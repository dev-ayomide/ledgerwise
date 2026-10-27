"""Contract: event types the backend emits are exactly the ones the UI handles."""

import re
from pathlib import Path

from backend.agent.events import EVENT_TYPES
from backend.agent.investigator import Investigator
from backend.gateway.local import LocalDuckDBGateway
from data.generate import generate

ROOT = Path(__file__).resolve().parents[2]


def test_ui_handles_every_event_type() -> None:
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    handled = set(re.findall(r'case "([a-z_]+)":', js))
    # query_started/result are both handled; every type must have a case
    assert set(EVENT_TYPES) <= handled


def test_stream_emits_known_types_in_order(tmp_path: Path) -> None:
    generate(tmp_path / "s")
    gateway = LocalDuckDBGateway(tmp_path / "s")
    try:
        events = list(Investigator(gateway).stream("q", "2026-10-21"))
    finally:
        gateway.close()
    types = [e.type for e in events]
    assert set(types) <= set(EVENT_TYPES)
    assert types[0] == "investigation_started" and types[-1] == "investigation_finished"
    for needed in ("plan", "hypothesis", "falsification_attempt", "falsification_result", "math_summary", "report", "actions_proposed"):
        assert needed in types
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    # every event serialises to JSON for SSE
    for event in events:
        event.model_dump_json()
