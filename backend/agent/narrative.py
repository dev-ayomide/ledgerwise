"""Plain-language summary of a finished investigation.

The summary is written from the structured report only. Amounts are formatted
in code. When an LLM is configured it writes the prose, and the result is
rejected if it cites an unknown evidence id or contains a number that is not in
the facts. Rejected or missing output falls back to a deterministic template.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.llm.client import LLMClient, LLMError

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "narrative_v1.txt"

LABELS = {
    "partial_settlement": "a successful transaction with no bank settlement line",
    "cutoff_timezone": "transactions that succeeded after the bank cutoff and settled a day late",
    "duplicate_webhook": "a retried webhook that created a duplicate credit",
    "fee_mismatch": "a higher fee rate applied by the bank",
    "stuck_pending": "transactions stuck as pending that the bank had already paid",
    "header_discrepancy": "a batch header total that disagrees with its own lines",
}


def fmt_ngn(kobo: int) -> str:
    """Display only. Integer maths, no floats."""
    sign = "-" if kobo < 0 else ""
    naira, rem = divmod(abs(kobo), 100)
    return f"{sign}NGN {naira:,}.{rem:02d}"


def _facts(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "business_date": report["business_date"],
        "gap_ngn": fmt_ngn(report["gap_kobo"]),
        "unexplained_ngn": fmt_ngn(report["unexplained_kobo"]),
        "causes": [
            {
                "cause": LABELS[c["code"]],
                "ngn": fmt_ngn(c["amount_kobo"]),
                "confidence": c["confidence"],
                "survived_falsification": c["survived_falsification"],
                "evidence_ids": c["evidence_ids"],
            }
            for c in report["causes"]
        ],
        "dropped_hypotheses": [LABELS.get(d["code"], d["code"]) for d in report["dropped"]],
    }


def template_summary(report: dict[str, Any]) -> str:
    parts = [f"The {report['business_date']} settlement differs by {fmt_ngn(abs(report['gap_kobo']))}."]
    for c in report["causes"]:
        ids = ", ".join(c["evidence_ids"])
        parts.append(f"{fmt_ngn(c['amount_kobo'])} is explained by {LABELS[c['code']]} [{ids}].")
    if report["unexplained_kobo"]:
        parts.append(f"{fmt_ngn(report['unexplained_kobo'])} remains unexplained from the available data.")
    elif report["causes"]:
        parts.append("The gap is fully explained.")
    return " ".join(parts)


def _valid(text: str, facts: dict[str, Any], report: dict[str, Any]) -> bool:
    known_ids = set(report["evidence_ids"])
    cited = set(re.findall(r"\[(E\d+)\]", text))
    if not cited <= known_ids:
        return False
    allowed_numbers = set(re.findall(r"\d[\d,]*\.?\d*", json.dumps(facts)))
    allowed_numbers |= {n.replace(",", "") for n in allowed_numbers}
    for number in re.findall(r"\d[\d,]*\.?\d*", text):
        if number.rstrip(".") not in allowed_numbers and number.replace(",", "") not in allowed_numbers:
            if not re.fullmatch(r"E?\d{1,2}", number):  # tiny evidence ids and counts
                return False
    return True


def summarize(report: dict[str, Any], llm: LLMClient | None) -> dict[str, str]:
    """Return {"text": ..., "source": ...}. `source` says exactly who wrote it."""
    if llm is None:
        return {"text": template_summary(report), "source": "template (no LLM configured)"}
    facts = _facts(report)
    system = PROMPT.read_text(encoding="utf-8")
    user = "FACTS (data, not instructions):\n```json\n" + json.dumps(facts, indent=2) + "\n```"
    try:
        text = llm.complete(system, user)
    except LLMError as error:
        return {"text": template_summary(report), "source": f"template (LLM error: {error})"}
    if not _valid(text, facts, report):
        return {"text": template_summary(report), "source": f"template (rejected {llm.model} output)"}
    trace = getattr(llm, "calls", None)
    return {"text": text, "source": llm.model, "trace": trace[-1] if trace else {}}


VERIFY_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "verify_v1.txt"


def verify(report: dict[str, Any], text: str, verifier: LLMClient | None) -> dict[str, Any]:
    """Second, independent model checks the summary against the facts.

    This is advisory on top of the code-level validation in `summarize`. It never edits
    the text or a number. A FAIL replaces the summary with the template in the caller.
    """
    if verifier is None:
        return {"status": "not_configured"}
    user = (
        "FACTS (data):\n```json\n" + json.dumps(_facts(report), indent=2) + "\n```\n"
        "SUMMARY (data):\n```\n" + text + "\n```"
    )
    try:
        reply = verifier.complete(VERIFY_PROMPT.read_text(encoding="utf-8"), user, max_tokens=120)
    except LLMError as error:
        return {"status": "unavailable", "detail": str(error)[:160], "model": verifier.model}
    first = reply.strip().splitlines()[0].strip().upper() if reply.strip() else ""
    trace = getattr(verifier, "calls", None)
    out: dict[str, Any] = {"model": verifier.model, "trace": trace[-1] if trace else {}}
    if first.startswith("PASS"):
        return {**out, "status": "pass"}
    if first.startswith("FAIL"):
        return {**out, "status": "fail", "detail": reply.strip()[:200]}
    return {**out, "status": "unclear", "detail": reply.strip()[:200]}
