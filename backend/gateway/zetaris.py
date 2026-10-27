"""Zetaris direct REST gateway.

The request shape matches the public getting-started client
(`RestChannel.run` in scripts/zetaris_sql.py): 

    POST {ZETARIS_REST_URL}/sql-editor/sqls/run
    headers: Authorization Bearer, X-Org-ID, X-Request-ID
    body: queryId, sql, source="SqlEditor", limit

That client has not been executed against a live instance from this repo.
Column names are taken from the payload only when it actually includes them.
The published helper reads `data` and does not document a column field.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

import httpx

from backend.gateway.models import QueryResult
from backend.guard.sql_guard import guard_sql
from backend.settings import load_dotenv

import os


class NotConfiguredError(RuntimeError):
    """Credentials or the instance URL are missing."""


class ZetarisError(RuntimeError):
    """The Zetaris HTTP call failed."""


class ZetarisGateway:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        load_dotenv()
        self.api_key = os.environ.get("ZETARIS_API_KEY", "")
        self.base_url = os.environ.get("ZETARIS_REST_URL", "").rstrip("/")
        self.org_id = os.environ.get("ZETARIS_ORG_ID", "")
        self._transport = transport
        self._timeout = timeout
        self.query_log: list[dict] = []

    def query(self, sql: str) -> QueryResult:
        self._require_config()
        guarded = guard_sql(sql, dialect="spark")  # Lightning SQL is Spark SQL
        body = {
            "queryId": str(uuid.uuid4()),
            "sql": guarded.sql,
            "source": "SqlEditor",
            "limit": 500,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Org-ID": self.org_id,
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/sql-editor/sqls/run"
        started = time.perf_counter()
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise ZetarisError(f"Cannot reach Zetaris at {self.base_url}: {error}") from error
        duration_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            detail = response.text[:300].replace(self.api_key, "[redacted]")
            raise ZetarisError(f"Zetaris HTTP {response.status_code}: {detail}")
        try:
            payload = response.json()
        except ValueError as error:
            raise ZetarisError("Zetaris did not return JSON.") from error
        columns, rows = _rows_from_payload(payload)
        entry = {
            "sql": guarded.sql,
            "tables": sorted(guarded.tables),
            "duration_ms": duration_ms,
            "row_count": len(rows),
            "engine": "zetaris-rest",
        }
        self.query_log.append(entry)
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            sql=guarded.sql,
            tables=sorted(guarded.tables),
            duration_ms=duration_ms,
            engine="zetaris-rest",
            log=entry,
        )

    def close(self) -> None:
        """Nothing to release: each call opens its own HTTP client."""

    def _require_config(self) -> None:
        missing: list[str] = []
        if not self.api_key:
            missing.append("ZETARIS_API_KEY")
        if not self.base_url.endswith("/api/v1.0"):
            missing.append("ZETARIS_REST_URL")
        if not re.fullmatch(r"[0-9]+", self.org_id or ""):
            missing.append("ZETARIS_ORG_ID")
        if missing:
            raise NotConfiguredError(
                "Zetaris is not configured ("
                + ", ".join(missing)
                + "). Create an API key in the Zetaris UI and store it in "
                ".env.local. Do not paste the key into chat. The local DuckDB "
                "gateway is for tests only."
            )


def _rows_from_payload(payload: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ZetarisError("Zetaris response was not a JSON object.")
    data = payload.get("data")
    if data is None:
        return [], []
    if not isinstance(data, list):
        raise ZetarisError("Zetaris response field 'data' was not a list.")

    columns: list[str] = []
    for key in ("headers", "columns", "columnNames", "fields"):
        raw = payload.get(key)
        if isinstance(raw, list) and raw:
            columns = [_column_label(item) for item in raw]
            break

    rows: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            if not columns:
                columns = list(item.keys())
            rows.append({key: _coerce(item.get(key)) for key in columns})
        elif isinstance(item, list):
            if not columns:
                columns = [f"c{index}" for index in range(len(item))]
            rows.append(
                {
                    column: _coerce(value)
                    for column, value in zip(columns, item, strict=False)
                }
            )
        else:
            rows.append({"c0": _coerce(item)})
    return columns, rows


def _column_label(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("name", "column", "field"):
            if item.get(key):
                return str(item[key])
    return str(item)


def _coerce(value: Any) -> Any:
    """Zetaris REST returns values as strings. Keep integers as integers.

    Exponent-formatted decimals are left as strings. Converting those with
    float would break kobo amounts.
    """

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value
