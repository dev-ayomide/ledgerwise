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

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
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
                headers={"Authorization": f"Bearer {self.api_key}"},
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


def build_llm() -> OpenAICompatibleClient | None:
    load_dotenv()
    key = os.environ.get("NVIDIA_API_KEY", "")
    base = os.environ.get("NVIDIA_BASE_URL", "")
    model = os.environ.get("NEMOTRON_MODEL", "")
    if not (key and base and model):
        return None
    return OpenAICompatibleClient(base_url=base, api_key=key, model=model)
