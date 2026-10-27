"""Check an LLM provider is reachable and list its model ids.

    .venv/bin/python -m backend.llm.probe nvidia     # lists Nemotron ids, then a 1-line test
    .venv/bin/python -m backend.llm.probe meterless

For NVIDIA, NEMOTRON_MODEL may be empty at first: the probe still lists the models
so you can copy a real id into .env.local.
"""

from __future__ import annotations

import os
import sys

from backend.llm.client import LLMError, OpenAICompatibleClient, build_llm, list_models
from backend.settings import load_dotenv


def main() -> None:
    load_dotenv()
    provider = sys.argv[1] if len(sys.argv) > 1 else "nvidia"
    client = build_llm(provider)
    if client is None and provider == "nvidia" and os.environ.get("NVIDIA_API_KEY") and os.environ.get("NVIDIA_BASE_URL"):
        client = OpenAICompatibleClient(
            base_url=os.environ["NVIDIA_BASE_URL"], api_key=os.environ["NVIDIA_API_KEY"], model=""
        )
    if client is None:
        raise SystemExit(f"{provider}: variables missing in .env.local (see .env.example).")
    try:
        ids = list_models(client)
    except LLMError as error:
        raise SystemExit(f"{provider}: {error}")
    shown = [i for i in ids if "nemotron" in i.lower()] if provider == "nvidia" else ids
    print(f"{provider}: {len(ids)} models. {'Nemotron ids' if provider == 'nvidia' else 'Ids'}:")
    for item in shown:
        print("  ", item)
    if not client.model:
        print("Set NEMOTRON_MODEL in .env.local to one of the ids above, then run this again.")
        return
    reply = client.complete("Reply with one short sentence.", "Say that the connection works.", max_tokens=40)
    print("test reply:", reply)
    print("call trace:", client.calls[-1])


if __name__ == "__main__":
    main()
