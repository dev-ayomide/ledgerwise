"""Typed investigation events. The SSE stream and the stored replay use this shape.

The browser UI mirrors these types in plain JavaScript (frontend/app.js).
`tests/test_events.py` pins the type list so the two cannot drift silently.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "investigation_started",
    "plan",
    "query_started",
    "query_result",
    "finding",
    "hypothesis",
    "falsification_attempt",
    "falsification_result",
    "math_summary",
    "report",
    "actions_proposed",
    "error",
    "investigation_finished",
]

EVENT_TYPES: tuple[str, ...] = EventType.__args__  # type: ignore[attr-defined]


class Event(BaseModel):
    type: EventType
    seq: int
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"))
    data: dict[str, Any] = Field(default_factory=dict)
