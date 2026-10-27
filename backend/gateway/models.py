"""Query results shared by every gateway."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    sql: str
    tables: list[str]
    duration_ms: int
    engine: str
    log: dict[str, Any] = Field(default_factory=dict)
