"""DuckDB stand-in that joins the three source files in one process.

This exists so tests and local development can run without a Zetaris
account. It is not the product. The submission demo uses ZetarisGateway.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import duckdb

from backend.gateway.models import QueryResult
from backend.guard.sql_guard import guard_sql

try:
    import signal
except ImportError:  # pragma: no cover
    signal = None  # type: ignore[assignment]


class GatewayError(RuntimeError):
    """The query could not be run."""


class LocalDuckDBGateway:
    def __init__(self, data_dir: Path, *, timeout_seconds: int = 15) -> None:
        self.data_dir = Path(data_dir)
        self.timeout_seconds = timeout_seconds
        self.query_log: list[dict] = []
        self._connection = self._open()

    def query(self, sql: str) -> QueryResult:
        guarded = guard_sql(sql, dialect="duckdb")
        started = time.perf_counter()

        def run() -> tuple[list[str], list[tuple]]:
            cursor = self._connection.execute(guarded.sql)
            columns = [item[0] for item in cursor.description]
            return columns, cursor.fetchall()

        try:
            columns, raw_rows = _run_with_timeout(run, self.timeout_seconds)
        except duckdb.Error as error:
            raise GatewayError(str(error)) from error
        duration_ms = int((time.perf_counter() - started) * 1000)
        rows = [
            {column: _cell(value) for column, value in zip(columns, raw)}
            for raw in raw_rows
        ]
        entry = {
            "sql": guarded.sql,
            "tables": sorted(guarded.tables),
            "duration_ms": duration_ms,
            "row_count": len(rows),
            "engine": "local-duckdb",
        }
        self.query_log.append(entry)
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            sql=guarded.sql,
            tables=sorted(guarded.tables),
            duration_ms=duration_ms,
            engine="local-duckdb",
            log=entry,
        )

    def close(self) -> None:
        self._connection.close()

    def _open(self) -> duckdb.DuckDBPyConnection:
        processor = self.data_dir / "processor.duckdb"
        events = self.data_dir / "events.duckdb"
        lines = self.data_dir / "bank" / "settlement_lines.parquet"
        batches = self.data_dir / "bank" / "settlement_batches.parquet"
        for path in (processor, events, lines, batches):
            if not path.is_file():
                raise GatewayError(f"Missing source file: {path}")
            if "'" in path.as_posix():
                raise GatewayError("Data paths cannot contain quotes.")

        connection = duckdb.connect()
        connection.execute(f"ATTACH '{processor.as_posix()}' AS proc_src (READ_ONLY)")
        connection.execute(f"ATTACH '{events.as_posix()}' AS events_src (READ_ONLY)")
        statements = [
            "CREATE SCHEMA processor",
            "CREATE TABLE processor.transactions AS SELECT * FROM proc_src.transactions",
            "CREATE TABLE processor.ledger_entries AS SELECT * FROM proc_src.ledger_entries",
            """
            CREATE TABLE processor.merchants AS
            SELECT
              id,
              name,
              CASE
                WHEN length(settlement_account_ref) <= 4 THEN '****'
                ELSE '******' || right(settlement_account_ref, 4)
              END AS settlement_account_ref
            FROM proc_src.merchants
            """,
            "CREATE SCHEMA bank",
            f"CREATE TABLE bank.settlement_lines AS SELECT * FROM read_parquet('{lines.as_posix()}')",
            f"CREATE TABLE bank.settlement_batches AS SELECT * FROM read_parquet('{batches.as_posix()}')",
            "CREATE SCHEMA events",
            "CREATE TABLE events.webhook_events AS SELECT * FROM events_src.webhook_events",
            "CREATE SCHEMA support",
            "CREATE TABLE support.tickets AS SELECT * FROM events_src.tickets",
            "DETACH proc_src",
            "DETACH events_src",
        ]
        for statement in statements:
            connection.execute(statement)
        _lock_down_external_access(connection)
        return connection


def _cell(value: object) -> object:
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _lock_down_external_access(connection: duckdb.DuckDBPyConnection) -> None:
    """The session already holds a copy of each source. Later SQL should not open files."""

    try:
        connection.execute("SET enable_external_access = false")
        connection.execute("SELECT COUNT(*) FROM processor.transactions").fetchone()
        connection.execute("SELECT COUNT(*) FROM bank.settlement_lines").fetchone()
    except Exception:
        try:
            connection.execute("SET enable_external_access = true")
        except Exception:
            return


def _run_with_timeout(fn, seconds: int):
    if (
        signal is None
        or threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGALRM")
    ):
        return fn()

    def handler(signum, frame):  # noqa: ARG001
        raise GatewayError(f"Query exceeded {seconds}s.")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        return fn()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
