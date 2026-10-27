"""Investigation agent loop.

Runs guarded diagnostic queries through a DataGateway, proposes causes,
tries to disprove each one with a second query, and reconciles the amounts in
code. `stream()` yields typed events for the UI; `investigate()` returns the
final `Investigation` for tests and the eval.

The reasoning here is deterministic rules over SQL results. An LLM, when
configured, only writes the plain-language summary from the structured result
(see backend/agent/narrative.py). It never produces amounts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from backend.agent import queries
from backend.agent.events import Event
from backend.agent.models import Investigation, RootCause
from backend.agent.narrative import summarize, template_summary, verify
from backend.gateway.models import QueryResult

MAX_QUERIES = 12
EVIDENCE_ROW_LIMIT = 50

SOURCE_OF_TABLE = {
    "processor": "Processor DB (Postgres)",
    "events": "Webhook log (Postgres)",
    "support": "Support tickets (Postgres)",
    "bank": "Bank settlement files (Parquet)",
}


def sources_for(tables: list[str]) -> list[str]:
    return sorted({SOURCE_OF_TABLE[t.split(".")[0]] for t in tables})


@dataclass
class _Check:
    code: str
    label: str
    why: str
    sql: Callable[[str], str]


@dataclass
class _Run:
    """Mutable state for one investigation."""

    gateway: Any
    seq: int = 0
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    query_count: int = 0

    def event(self, type_: str, **data: Any) -> Event:
        self.seq += 1
        return Event(type=type_, seq=self.seq, data=data)  # type: ignore[arg-type]

    def run_query(self, purpose: str, sql: str) -> tuple[QueryResult, str, list[Event]]:
        """Run one guarded query and return (result, evidence id, events to emit)."""
        if self.query_count >= MAX_QUERIES + 6:
            raise RuntimeError("Query budget exhausted.")
        self.query_count += 1
        evidence_id = f"E{len(self.evidence) + 1}"
        started = self.event("query_started", evidence_id=evidence_id, purpose=purpose, sql=sql)
        result = self.gateway.query(sql)
        self.evidence[evidence_id] = {
            "id": evidence_id,
            "purpose": purpose,
            "sql": result.sql,
            "tables": result.tables,
            "sources": sources_for(result.tables),
            "engine": result.engine,
            "row_count": result.row_count,
            "duration_ms": result.duration_ms,
            "columns": result.columns,
            "rows": result.rows[:EVIDENCE_ROW_LIMIT],
            "truncated": result.row_count > EVIDENCE_ROW_LIMIT,
        }
        done = self.event("query_result", **self.evidence[evidence_id])
        return result, evidence_id, [started, done]


CHECKS: dict[str, _Check] = {
    "duplicate_webhook": _Check(
        "duplicate_webhook",
        "Duplicate webhook credits",
        "Two processor successes for one reference while the bank paid once.",
        queries.duplicate_webhooks,
    ),
    "cutoff_timezone": _Check(
        "cutoff_timezone",
        "Bank cutoff and timezone shift",
        "Successes after the 20:00 UTC cutoff settle on the next value date.",
        queries.cutoff_violations,
    ),
    "fee_mismatch": _Check(
        "fee_mismatch",
        "Fee rate mismatch",
        "Bank lines slightly below processor net point to a different fee rate.",
        queries.fee_mismatches,
    ),
    "partial_settlement": _Check(
        "partial_settlement",
        "Missing bank line",
        "Processor successes with no bank line on any value date.",
        queries.partial_settlements,
    ),
    "stuck_pending": _Check(
        "stuck_pending",
        "Stuck pending transactions",
        "The bank paid something the processor still shows as pending.",
        queries.stuck_pending,
    ),
    "header_discrepancy": _Check(
        "header_discrepancy",
        "Batch header vs lines",
        "Gap is zero on lines, so compare the declared batch total with its lines.",
        queries.batch_header_gap,
    ),
}


class Investigator:
    def __init__(self, gateway, llm=None, verifier=None) -> None:
        self.gateway = gateway
        self.llm = llm
        self.verifier = verifier
        self.last_run: _Run | None = None
        self.last_investigation: Investigation | None = None

    # -- public API ---------------------------------------------------------

    def investigate(self, question: str, business_date: str) -> Investigation:
        for _ in self.stream(question, business_date):
            pass
        assert self.last_investigation is not None
        return self.last_investigation

    def stream(self, question: str, business_date: str) -> Iterator[Event]:
        started = time.perf_counter()
        run = _Run(gateway=self.gateway)
        self.last_run = run
        day = business_date
        engine = ""

        yield run.event("investigation_started", question=question, business_date=day)

        # understand: headline numbers
        result, headline_id, events = run.run_query(
            "Headline numbers: expected processor net vs bank lines for the value date",
            queries.headline_gap(day),
        )
        yield from events
        engine = result.engine
        row = result.rows[0]
        gap_kobo = int(row["gap_kobo"])
        expected_kobo = int(row["expected_kobo"])
        actual_kobo = int(row["actual_kobo"])
        yield run.event(
            "finding",
            text=(
                f"Processor expects {expected_kobo} kobo from {row['success_count']} successful "
                f"transactions. The bank settled {actual_kobo} kobo across {row['line_count']} lines. "
                f"Gap: {gap_kobo} kobo."
            ),
            evidence_ids=[headline_id],
        )

        # plan
        if gap_kobo > 0:
            order = ["partial_settlement", "cutoff_timezone", "duplicate_webhook", "fee_mismatch"]
            direction = "The processor expects more than the bank paid."
        elif gap_kobo < 0:
            order = ["stuck_pending"]
            direction = "The bank paid more than the processor expects."
        else:
            order = ["header_discrepancy"]
            direction = "Line totals agree, so the check moves to the batch header."
        yield run.event(
            "plan",
            direction=direction,
            checks=[{"code": c, "label": CHECKS[c].label, "why": CHECKS[c].why} for c in order],
        )

        # investigate + hypothesize
        causes: list[RootCause] = []
        for code in order:
            check = CHECKS[code]
            result, evidence_id, events = run.run_query(check.label, check.sql(day))
            yield from events
            cause = self._cause_from_rows(code, result, evidence_id)
            if cause is None:
                yield run.event(
                    "finding",
                    text=f"{check.label}: nothing found for this date.",
                    evidence_ids=[evidence_id],
                )
                continue
            yield run.event(
                "finding",
                text=cause.summary,
                evidence_ids=[evidence_id],
            )
            yield run.event(
                "hypothesis",
                code=code,
                label=check.label,
                amount_kobo=cause.amount_kobo,
                evidence_ids=[evidence_id],
            )
            causes.append(cause)

        # falsify
        kept: list[RootCause] = []
        dropped: list[dict[str, Any]] = []
        for cause in causes:
            yield run.event(
                "falsification_attempt",
                code=cause.code,
                approach=FALSIFY_APPROACH[cause.code],
            )
            try:
                survived, note, extra_id, events = self._falsify(run, cause, day)
            except Exception as error:  # a failed disproof must not look like a pass
                survived, note, extra_id, events = None, f"Falsification query failed: {error}", None, []
            yield from events
            cause.survived_falsification = survived
            cause.falsification_note = note
            if extra_id:
                cause.evidence_ids.append(extra_id)
            yield run.event(
                "falsification_result",
                code=cause.code,
                survived=survived,
                note=note,
                evidence_ids=[extra_id] if extra_id else [],
            )
            if survived is False:
                dropped.append({"code": cause.code, "amount_kobo": cause.amount_kobo, "note": note})
            else:
                kept.append(cause)

        # reconcile_math: in code, never by the model
        abs_gap = abs(gap_kobo)
        if gap_kobo == 0:
            header = next((c for c in kept if c.code == "header_discrepancy"), None)
            unexplained = header.amount_kobo if header else 0
            explained = 0
            kept_for_math = [c for c in kept if c.code != "header_discrepancy"]
        else:
            kept_for_math = kept
            explained = sum(c.amount_kobo for c in kept_for_math)
            unexplained = abs_gap - explained

        for cause in kept:
            cause.confidence = _confidence(cause, unexplained)

        math = {
            "gap_kobo": gap_kobo,
            "explained_kobo": explained,
            "unexplained_kobo": unexplained,
            "by_cause": [{"code": c.code, "amount_kobo": c.amount_kobo} for c in kept_for_math],
            "note": "Computed in code from query results. The model never does this arithmetic.",
        }
        yield run.event("math_summary", **math)

        investigation = Investigation(
            question=question,
            business_date=business_date,
            gap_kobo=gap_kobo,
            expected_kobo=expected_kobo,
            actual_kobo=actual_kobo,
            root_causes=kept,
            unexplained_kobo=unexplained,
            engine=engine,
            duration_ms=int((time.perf_counter() - started) * 1000),
            dropped=dropped,
            query_count=run.query_count,
        )
        self.last_investigation = investigation
        report = build_report(investigation, run.evidence)
        report["narrative"] = summarize(report, self.llm)
        if self.verifier is not None and not report["narrative"]["source"].startswith("template"):
            check = verify(report, report["narrative"]["text"], self.verifier)
            report["narrative"]["verification"] = check
            if check["status"] == "fail":
                report["narrative"] = {
                    "text": template_summary(report),
                    "source": "template (verifier rejected the model summary)",
                    "verification": check,
                }
        yield run.event("report", **report)
        yield run.event("actions_proposed", actions=propose_actions(investigation))
        yield run.event(
            "investigation_finished",
            duration_ms=investigation.duration_ms,
            query_count=run.query_count,
            engine=engine,
        )

    # -- helpers ------------------------------------------------------------

    def _cause_from_rows(self, code: str, result: QueryResult, evidence_id: str) -> RootCause | None:
        rows = result.rows
        if code == "duplicate_webhook":
            rows = [r for r in rows if int(r.get("gap_kobo", 0)) > 0]
            if not rows:
                return None
            total = sum(int(r["gap_kobo"]) for r in rows)
            refs = ", ".join(str(r["matched_reference"]) for r in rows)
            summary = (
                f"Reference {refs} has {rows[0]['proc_count']} processor successes but "
                f"{rows[0]['bank_count']} bank line. The extra credit is {total} kobo."
            )
        elif code == "cutoff_timezone":
            if not rows:
                return None
            total = sum(int(r["net_kobo"]) for r in rows)
            summary = (
                f"{len(rows)} transaction(s) succeeded after the 20:00 UTC bank cutoff. "
                f"The bank paid them on a later value date. Total {total} kobo."
            )
        elif code == "fee_mismatch":
            rows = [r for r in rows if int(r.get("gap_kobo", 0)) > 0]
            if not rows:
                return None
            total = sum(int(r["gap_kobo"]) for r in rows)
            summary = (
                f"{len(rows)} bank line(s) are below processor net by a small amount, "
                f"which points to a higher fee rate at the bank. Total {total} kobo."
            )
        elif code == "partial_settlement":
            if not rows:
                return None
            total = sum(int(r["gap_kobo"]) for r in rows)
            summary = (
                f"{len(rows)} processor success(es) have no bank line on any value date. "
                f"Total {total} kobo."
            )
        elif code == "stuck_pending":
            if not rows:
                return None
            total = sum(int(r["amount_kobo"]) for r in rows)
            summary = (
                f"{len(rows)} bank line(s) paid transactions the processor still shows as pending. "
                f"Total {total} kobo."
            )
        elif code == "header_discrepancy":
            rows = [r for r in rows if int(r.get("header_gap_kobo", 0)) != 0]
            if not rows:
                return None
            total = sum(abs(int(r["header_gap_kobo"])) for r in rows)
            summary = (
                f"Batch {rows[0]['batch_ref']} declares a total that differs from its own lines "
                f"by {rows[0]['header_gap_kobo']} kobo."
            )
        else:  # pragma: no cover
            return None
        return RootCause(
            code=code,
            amount_kobo=total,
            summary=summary,
            evidence_rows=rows,
            sql_used=result.sql,
            evidence_ids=[evidence_id],
        )

    def _falsify(
        self, run: _Run, cause: RootCause, day: str
    ) -> tuple[bool | None, str, str | None, list[Event]]:
        rows = cause.evidence_rows
        code = cause.code
        if code == "duplicate_webhook":
            refs = [str(r["matched_reference"]) for r in rows]
            result, eid, events = run.run_query(
                "Falsify duplicate: is this a webhook retry or two distinct payments?",
                queries.falsify_duplicate(refs),
            )
            seen = {str(r["transaction_reference"]): int(r["attempts"]) for r in result.rows}
            ok = all(seen.get(ref, 0) >= 2 for ref in refs)
            note = (
                "The webhook log shows a retry sequence (attempt 1 then 2) for each reference, "
                "so these are one payment delivered twice, not two payments."
                if ok
                else "The webhook log does not show a retry sequence. These may be distinct payments."
            )
            return ok, note, eid, events
        if code == "cutoff_timezone":
            line_ids = [str(r["later_line_id"]) for r in rows]
            result, eid, events = run.run_query(
                "Falsify cutoff: did the bank pay the full net on the later date?",
                queries.falsify_cutoff(line_ids),
            )
            paid = sorted(int(r["amount_kobo"]) for r in result.rows)
            nets = sorted(int(r["net_kobo"]) for r in rows)
            ok = paid == nets
            note = (
                "Each later bank line equals the processor net exactly, so the money arrived "
                "one day late rather than going missing."
                if ok
                else "The later bank lines do not match the processor net. This is not only a timing shift."
            )
            return ok, note, eid, events
        if code == "fee_mismatch":
            refs = [str(r["matched_reference"]) for r in rows]
            result, eid, events = run.run_query(
                "Falsify fee mismatch: is the shortfall a consistent rate difference?",
                queries.falsify_fee(refs),
            )
            amount_by_ref = {str(r["reference"]): (int(r["amount_kobo"]), int(r["fee_kobo"])) for r in result.rows}
            implied: set[int] = set()
            for r in rows:
                amount, fee = amount_by_ref.get(str(r["matched_reference"]), (0, 0))
                if amount:
                    implied.add(int(r["gap_kobo"]) * 10_000 // amount)
            ok = len(implied) == 1
            note = (
                f"Every short line is off by the same {implied.copy().pop()} basis points of the "
                "payment amount. That is a rate difference, not random loss."
                if ok
                else "The shortfalls do not share one rate difference, so fees alone do not explain them."
            )
            return ok, note, eid, events
        if code == "partial_settlement":
            amounts = [int(r["proc_net"]) for r in rows]
            result, eid, events = run.run_query(
                "Falsify missing line: does an unmatched bank line carry this amount?",
                queries.falsify_partial(amounts),
            )
            ok = result.row_count == 0
            note = (
                "No unmatched bank line on any date carries the missing amount, so the money "
                "was not settled under a different reference."
                if ok
                else f"{result.row_count} unmatched bank line(s) carry the same amount. The payment may have been matched wrongly."
            )
            return ok, note, eid, events
        if code == "stuck_pending":
            refs = [str(r["matched_reference"]) for r in rows]
            result, eid, events = run.run_query(
                "Falsify stuck pending: does the webhook log show the processor failing to confirm?",
                queries.falsify_stuck(refs),
            )
            failing = {str(r["transaction_reference"]) for r in result.rows if int(r["http_status"]) >= 500}
            ok = all(ref in failing for ref in refs)
            note = (
                "The webhook log shows server errors for each reference, so the processor "
                "timed out and never recorded the success the bank paid."
                if ok
                else "Some references show no server error. The pending state has another cause."
            )
            return ok, note, eid, events
        if code == "header_discrepancy":
            result, eid, events = run.run_query(
                "Falsify header gap: recount the batch from its own lines",
                queries.falsify_header(day),
            )
            row = result.rows[0] if result.rows else None
            ok = bool(row) and int(row["declared_total"]) - int(row["actual_total"]) == int(rows[0]["header_gap_kobo"])
            note = (
                "A fresh recount confirms the declared total differs from the lines. Nothing in the "
                "available data explains why, so this stays unexplained."
                if ok
                else "The recount does not reproduce the header gap."
            )
            return ok, note, eid, events
        raise ValueError(f"No falsifier for {code}")  # pragma: no cover


FALSIFY_APPROACH = {
    "duplicate_webhook": "Check the webhook log: a real duplicate shows a retry sequence for one reference.",
    "cutoff_timezone": "Check the later bank lines: they should carry exactly the processor net.",
    "fee_mismatch": "Check that every short line implies the same rate difference.",
    "partial_settlement": "Search for an unmatched bank line carrying the missing amount.",
    "stuck_pending": "Check the webhook log for server errors on these references.",
    "header_discrepancy": "Recount the batch from its lines.",
}


def _confidence(cause: RootCause, unexplained: int) -> str:
    """Derived from checkable signals, never from model self-report."""
    if cause.survived_falsification is not True:
        return "low"
    if not cause.evidence_rows:
        return "low"
    if unexplained == 0:
        return "high"
    return "medium"


def build_report(inv: Investigation, evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(inv.root_causes, key=lambda c: c.amount_kobo, reverse=True)
    return {
        "business_date": inv.business_date,
        "gap_kobo": inv.gap_kobo,
        "expected_kobo": inv.expected_kobo,
        "actual_kobo": inv.actual_kobo,
        "unexplained_kobo": inv.unexplained_kobo,
        "causes": [
            {
                "code": c.code,
                "amount_kobo": c.amount_kobo,
                "summary": c.summary,
                "confidence": c.confidence,
                "survived_falsification": c.survived_falsification,
                "falsification_note": c.falsification_note,
                "evidence_ids": c.evidence_ids,
                "row_count": len(c.evidence_rows),
            }
            for c in ranked
        ],
        "dropped": inv.dropped,
        "query_count": inv.query_count,
        "evidence_ids": sorted(evidence, key=lambda e: int(e[1:])),
    }


ACTION_TEMPLATES = {
    "partial_settlement": (
        "Dispute missing settlement line with the bank",
        "Subject: Missing settlement line, value date {date}\n\nOur ledger shows a successful transaction of {amount} kobo with no matching line in your settlement file. "
        "No line on any value date carries this amount. Please confirm whether it was paid and under which reference. Evidence: {evidence}.",
    ),
    "cutoff_timezone": (
        "Note timing difference, no recovery needed",
        "These {amount} kobo settled one value date late because they succeeded after the 20:00 UTC bank cutoff (21:00 West Africa Time). "
        "No money is missing. Add a cutoff-aware rule to the daily reconciliation. Evidence: {evidence}.",
    ),
    "duplicate_webhook": (
        "Request reversal of the duplicate ledger credit",
        "Reversal request for {date}: a retried webhook created a second success and ledger credit worth {amount} kobo. "
        "The bank paid once. Reverse the second credit and enforce idempotency on the webhook handler. Evidence: {evidence}.",
    ),
    "fee_mismatch": (
        "Raise fee-rate dispute with the bank",
        "The bank deducted a higher fee rate than the merchant's configured tier on the lines in evidence, {amount} kobo in total. "
        "Ask the bank to confirm the tier or refund the difference. Evidence: {evidence}.",
    ),
    "stuck_pending": (
        "Mark pending transactions as settled after review",
        "The bank paid {amount} kobo for transactions our processor still shows as pending after webhook timeouts. "
        "Review and post the missing ledger entries. Evidence: {evidence}.",
    ),
    "header_discrepancy": (
        "Ask the bank to correct the batch header",
        "The declared batch total differs from the sum of its lines by {amount} kobo. "
        "Request a corrected header or an explanation. This remains unexplained from our data. Evidence: {evidence}.",
    ),
}


def propose_actions(inv: Investigation) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for cause in sorted(inv.root_causes, key=lambda c: c.amount_kobo, reverse=True):
        title, body = ACTION_TEMPLATES[cause.code]
        actions.append(
            {
                "id": f"act_{cause.code}",
                "code": cause.code,
                "title": title,
                "amount_kobo": cause.amount_kobo,
                "draft": body.format(
                    date=inv.business_date,
                    amount=cause.amount_kobo,
                    evidence=", ".join(cause.evidence_ids),
                ),
                "status": "proposed",
                "executes_anything": False,
            }
        )
    return actions
