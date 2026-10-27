"""LLM client behind a small interface.

The default model is NVIDIA Nemotron through an OpenAI-compatible chat
endpoint. Nothing here guesses a model id or URL: all three values come from
the environment (NVIDIA_API_KEY, NVIDIA_BASE_URL, NEMOTRON_MODEL). When any is
missing `build_llm()` returns None and callers fall back to deterministic text.
"""

from __future__ import annotations

import os
import time
from typing import Protocol

import httpx

from backend.settings import load_dotenv


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int = 600) -> str: ...


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    """POST {base_url}/chat/completions. Works for NVIDIA NIM and Meterless Nightshift."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
        provider: str = "nvidia",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.provider = provider
        self.calls: list[dict] = []  # trace: latency and token counts per call

    def complete(self, system: str, user: str, *, max_tokens: int = 600) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}", **self.extra_headers},
                timeout=self.timeout,
            )
        except httpx.HTTPError as error:
            raise LLMError(f"Cannot reach the model endpoint: {error}") from error
        if response.status_code >= 400:
            raise LLMError(f"Model endpoint HTTP {response.status_code}: {response.text[:200]}")
        payload = response.json()
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError("Unexpected model response shape.") from error
        self.calls.append(
            {
                "model": self.model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "usage": payload.get("usage", {}),
            }
        )
        return str(text).strip()


def build_llm(provider: str | None = None) -> OpenAICompatibleClient | None:
    """Build the configured client, or None when its variables are not all set.

    LLM_PROVIDER picks `nvidia` (default, Nemotron) or `meterless` (Nightshift).
    """
    load_dotenv()
    provider = (provider or os.environ.get("LLM_PROVIDER", "nvidia")).lower()
    if provider == "meterless":
        key = os.environ.get("METERLESS_API_KEY", "")
        base = os.environ.get("METERLESS_BASE_URL", "")
        model = os.environ.get("METERLESS_MODEL", "meterless/auto")
        if not (key and base):
            return None
        return OpenAICompatibleClient(
            base_url=base,
            api_key=key,
            model=model,
            provider="meterless",
            # Headers Meterless documents for chat requests.
            extra_headers={"meterless-app": "ledgerwise", "meterless-scope": "user"},
        )
    key = os.environ.get("NVIDIA_API_KEY", "")
    base = os.environ.get("NVIDIA_BASE_URL", "")
    model = os.environ.get("NEMOTRON_MODEL", "")
    if not (key and base and model):
        return None
    return OpenAICompatibleClient(base_url=base, api_key=key, model=model)


def list_models(client: OpenAICompatibleClient) -> list[str]:
    """GET {base_url}/models. Use this to read real model ids instead of guessing them."""
    response = httpx.get(
        f"{client.base_url}/models",
        headers={"Authorization": f"Bearer {client.api_key}", **client.extra_headers},
        timeout=client.timeout,
    )
    if response.status_code >= 400:
        raise LLMError(f"Model list HTTP {response.status_code}: {response.text[:200]}")
    return sorted(str(item.get("id", "")) for item in response.json().get("data", []))
