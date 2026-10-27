import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.generate import generate


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from backend.app import main

    generate(tmp_path / "g")
    monkeypatch.setenv("LEDGERWISE_GATEWAY", "local")
    monkeypatch.setattr(main, "GENERATED", tmp_path / "g")
    monkeypatch.setattr(main, "STORE", tmp_path / "store")
    monkeypatch.setattr(main, "_gateway", None)
    monkeypatch.setattr(main, "_dashboard_cache", None)
    monkeypatch.setattr(main, "build_llm", lambda: None)
    yield TestClient(main.app)
    if main._gateway is not None:
        main._gateway.close()


def _events(response) -> list[dict]:
    return [json.loads(c[6:]) for c in response.text.split("\n\n") if c.startswith("data: ")]


def test_investigate_stream_then_approve_and_export(client) -> None:
    r = client.post("/api/investigate", json={"question": "why", "business_date": "2026-10-21"})
    events = _events(r)
    assert events[-1]["type"] == "investigation_finished"
    inv_id = events[0]["data"]["investigation_id"]
    actions = next(e for e in events if e["type"] == "actions_proposed")["data"]["actions"]
    assert actions and all(a["executes_anything"] is False for a in actions)

    approved = client.post(f"/api/investigations/{inv_id}/actions/{actions[0]['id']}", json={"decision": "approve"}).json()
    assert approved["executed"] is False and approved["draft"]
    rejected = client.post(f"/api/investigations/{inv_id}/actions/{actions[1]['id']}", json={"decision": "reject"}).json()
    assert rejected["draft"] is None

    assert "Evidence queries" in client.get(f"/api/investigations/{inv_id}/export").text
    replay = _events(client.get(f"/api/investigations/{inv_id}/replay?delay=0"))
    assert [e["type"] for e in replay] == [e["type"] for e in events]


def test_bad_inputs_are_rejected(client) -> None:
    assert client.post("/api/investigate", json={"question": "x", "business_date": "not-a-date"}).status_code == 400
    assert client.get("/api/investigations/..%2Fetc/replay").status_code in (400, 404)
    assert client.post("/api/investigations/zzzz/actions/a", json={"decision": "approve"}).status_code == 404


def test_dashboard_flags_demo_gap(client) -> None:
    rows = client.get("/api/dashboard").json()
    demo = next(r for r in rows if r["business_date"] == "2026-10-21")
    assert demo["gap_kobo"] == 420_000_000
