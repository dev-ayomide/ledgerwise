"""Pydantic models for investigation results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RootCause(BaseModel):
    code: str  # e.g. "duplicate_webhook", "cutoff_timezone", "fee_mismatch", "partial_settlement", "stuck_pending"
    amount_kobo: int
    summary: str
    evidence_rows: list[dict[str, Any]] = Field(default_factory=list)
    sql_used: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    survived_falsification: bool | None = None
    falsification_note: str = ""
    confidence: str = "unrated"  # high | medium | low, derived from checkable signals


class Investigation(BaseModel):
    question: str
    business_date: str  # YYYY-MM-DD
    gap_kobo: int
    expected_kobo: int
    actual_kobo: int
    root_causes: list[RootCause] = Field(default_factory=list)
    unexplained_kobo: int
    engine: str
    duration_ms: int
    dropped: list[dict[str, Any]] = Field(default_factory=list)  # hypotheses that failed falsification
    query_count: int = 0
