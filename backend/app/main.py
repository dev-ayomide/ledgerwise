"""FastAPI app: SSE investigation stream, dashboard, approvals, export, replay.

Run:  LEDGERWISE_GATEWAY=zetaris .venv/bin/uvicorn backend.app.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.agent import queries
from backend.agent.events import EVENT_TYPES, Event
from backend.agent.investigator import Investigator
from backend.agent.narrative import fmt_ngn
from backend.llm.client import build_llm
from backend.settings import ROOT, load_dotenv

load_dotenv()

STORE = ROOT / "data" / "investigations"
FRONTEND = ROOT / "frontend"
GENERATED = ROOT / "data" / "generated"

app = FastAPI(title="Ledgerwise")

_gateway: Any = None
_gateway_lock = threading.Lock()
_dashboard_cache: list[dict[str, Any]] | None = None
_dashboard_lock = threading.Lock()


def _engine_name() -> str:
    wanted = os.environ.get("LEDGERWISE_GATEWAY", "").lower()
    if wanted in {"zetaris", "local"}:
        return wanted
    return "zetaris" if os.environ.get("ZETARIS_API_KEY") else "local"


def get_gateway() -> Any:
    """One gateway per process. No silent fallback: if Zetaris is asked for and fails, it errors."""
    global _gateway
    if _gateway is None:
        if _engine_name() == "zetaris":
            from backend.gateway.zetaris import ZetarisGateway

            gateway = ZetarisGateway()
            gateway._require_config()
            _gateway = gateway
        else:
            from backend.gateway.local import LocalDuckDBGateway

            _gateway = LocalDuckDBGateway(GENERATED)
    return _gateway


def _scenarios() -> list[dict[str, Any]]:
    data = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    return data["scenarios"]


class InvestigateRequest(BaseModel):
    question: str
    business_date: str


@app.get("/api/config")
def config() -> dict[str, Any]:
    llm = build_llm()
    return {
        "gateway": _engine_name(),
        "llm": llm.model if llm else None,
        "event_types": list(EVENT_TYPES),
    }


def _headline(scenario: dict[str, Any]) -> dict[str, Any]:
    gateway = get_gateway()
    sql = queries.headline_gap(scenario["business_date"])
    if _engine_name() == "local":
        with _gateway_lock:
            result = gateway.query(sql)
    else:
        result = gateway.query(sql)
    row = result.rows[0]
    return {
        "business_date": scenario["business_date"],
        "scenario_id": scenario["id"],
        "question": scenario["question"],
        "expected_kobo": int(row["expected_kobo"]),
        "actual_kobo": int(row["actual_kobo"]),
        "gap_kobo": int(row["gap_kobo"]),
        "expected": fmt_ngn(int(row["expected_kobo"])),
        "actual": fmt_ngn(int(row["actual_kobo"])),
        "gap": fmt_ngn(int(row["gap_kobo"])),
    }


def _build_dashboard() -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor

    scenarios = _scenarios()
    workers = 1 if _engine_name() == "local" else 4
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_headline, scenarios))
    rows.sort(key=lambda r: r["business_date"], reverse=True)
    return rows


@app.on_event("startup")
def _warm_dashboard() -> None:
    """Fill the cache in the background so the first page load is instant."""

    def work() -> None:
        global _dashboard_cache
        try:
            with _dashboard_lock:
                if _dashboard_cache is None:
                    _dashboard_cache = _build_dashboard()
        except Exception:  # the endpoint retries and reports the real error
            pass

    threading.Thread(target=work, daemon=True).start()


@app.get("/api/dashboard")
def dashboard() -> list[dict[str, Any]]:
    """Headline numbers for each demo date, from the same gateway the agent uses."""
    global _dashboard_cache
    with _dashboard_lock:
        if _dashboard_cache is None:
            _dashboard_cache = _build_dashboard()
    return _dashboard_cache


def _sse(event: Event) -> str:
    return f"data: {event.model_dump_json()}\n\n"


def _save(investigation_id: str, question: str, date: str, engine: str, events: list[Event]) -> None:
    STORE.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": investigation_id,
        "question": question,
        "business_date": date,
        "engine": engine,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "events": [e.model_dump(mode="json") for e in events],
    }
    (STORE / f"{investigation_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run(request: InvestigateRequest) -> Iterator[str]:
    investigation_id = uuid.uuid4().hex[:8]
    events: list[Event] = []
    try:
        gateway = get_gateway()
        investigator = Investigator(gateway, llm=build_llm())
        with _gateway_lock if _engine_name() == "local" else _NullLock():
            for event in investigator.stream(request.question, request.business_date):
                if event.type == "investigation_started":
                    event.data["investigation_id"] = investigation_id
                events.append(event)
                yield _sse(event)
    except Exception as error:  # surfaced in the timeline, never swallowed
        failure = Event(type="error", seq=len(events) + 1, data={"message": str(error)[:400]})
        events.append(failure)
        yield _sse(failure)
        return
    engine = investigator.last_investigation.engine if investigator.last_investigation else ""
    _save(investigation_id, request.question, request.business_date, engine, events)


class _NullLock:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


@app.post("/api/investigate")
def investigate(request: InvestigateRequest) -> StreamingResponse:
    if not _valid_date(request.business_date):
        raise HTTPException(400, "business_date must be YYYY-MM-DD")
    return StreamingResponse(_run(request), media_type="text/event-stream")


def _valid_date(value: str) -> bool:
    import datetime as dt

    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _load(investigation_id: str) -> dict[str, Any]:
    if not investigation_id.isalnum():
        raise HTTPException(400, "bad id")
    path = STORE / f"{investigation_id}.json"
    if not path.is_file():
        raise HTTPException(404, "unknown investigation")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/investigations")
def list_investigations() -> list[dict[str, Any]]:
    if not STORE.is_dir():
        return []
    items = []
    for path in sorted(STORE.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.name.endswith(".actions.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append({k: data[k] for k in ("id", "question", "business_date", "engine", "created_at")})
    return items[:20]


@app.get("/api/investigations/{investigation_id}/replay")
async def replay(investigation_id: str, delay: float = 0.4) -> StreamingResponse:
    data = _load(investigation_id)

    async def gen():
        for raw in data["events"]:
            yield f"data: {json.dumps(raw)}\n\n"
            await asyncio.sleep(min(max(delay, 0.0), 2.0))

    return StreamingResponse(gen(), media_type="text/event-stream")


class Decision(BaseModel):
    decision: str  # approve | reject


@app.post("/api/investigations/{investigation_id}/actions/{action_id}")
def decide(investigation_id: str, action_id: str, body: Decision) -> dict[str, Any]:
    """Record a human decision. Approving writes a draft document. Nothing is executed."""
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve or reject")
    data = _load(investigation_id)
    actions = next(
        (e["data"]["actions"] for e in data["events"] if e["type"] == "actions_proposed"), []
    )
    action = next((a for a in actions if a["id"] == action_id), None)
    if action is None:
        raise HTTPException(404, "unknown action")
    path = STORE / f"{investigation_id}.actions.json"
    decisions = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    decisions[action_id] = {
        "decision": body.decision,
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "draft": action["draft"] if body.decision == "approve" else None,
        "executed": False,
    }
    path.write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    return decisions[action_id]


@app.get("/api/investigations/{investigation_id}/export")
def export(investigation_id: str) -> PlainTextResponse:
    data = _load(investigation_id)
    report = next(e["data"] for e in data["events"] if e["type"] == "report")
    lines = [
        f"# Settlement investigation, {report['business_date']}",
        "",
        f"Question: {data['question']}",
        f"Data engine: {data['engine']}",
        "",
        f"Gap: {fmt_ngn(report['gap_kobo'])}. Unexplained: {fmt_ngn(report['unexplained_kobo'])}.",
        "",
        f"Summary ({report['narrative']['source']}): {report['narrative']['text']}",
        "",
        "## Causes",
    ]
    for c in report["causes"]:
        lines += [
            f"- **{c['code']}**: {fmt_ngn(c['amount_kobo'])}, confidence {c['confidence']}. {c['summary']}",
            f"  - Falsification: {c['falsification_note']}",
            f"  - Evidence: {', '.join(c['evidence_ids'])}",
        ]
    lines += ["", "## Evidence queries"]
    for e in data["events"]:
        if e["type"] == "query_result":
            d = e["data"]
            lines += [f"### {d['id']}: {d['purpose']}", f"Sources: {', '.join(d['sources'])}. Rows: {d['row_count']}.", "```sql", d["sql"], "```"]
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
