"""Load local env files without overriding the process environment."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOADED = False


def load_dotenv() -> None:
    """Read `.env`, then `.env.local`. Existing process variables stay put."""

    global _LOADED
    if _LOADED:
        return
    preexisting = set(os.environ)
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.is_file():
            continue
        for key, value in _parse(path):
            if key in preexisting:
                continue
            os.environ[key] = value
    _LOADED = True


def _parse(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        pairs.append((key.strip(), value))
    return pairs
