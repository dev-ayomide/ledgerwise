"""Load the generated synthetic sources into two Postgres databases for Zetaris.

Zetaris registers JDBC sources and Parquet/CSV files. It cannot read DuckDB
files, so the processor and events/support sources live in Postgres for the
federated demo. Only ledgerwise_* databases are created. Re-running recreates the tables
in those two databases and touches nothing else.

    .venv/bin/python -m data.load_postgres
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "generated"

PG_ARGS = ["-h", os.environ.get("LEDGERWISE_PG_HOST", "127.0.0.1"), "-p", os.environ.get("LEDGERWISE_PG_PORT", "5432")]

PG_TYPES = {
    "VARCHAR": "text",
    "BIGINT": "bigint",
    "INTEGER": "integer",
    "TIMESTAMP": "timestamp",
    "DATE": "date",
}

# database -> (duckdb file, source table -> target table)
LAYOUT: dict[str, tuple[str, dict[str, str]]] = {
    "ledgerwise_processor": (
        "processor.duckdb",
        {"transactions": "transactions", "ledger_entries": "ledger_entries", "merchants": "merchants"},
    ),
    "ledgerwise_events": (
        "events.duckdb",
        {"webhook_events": "webhook_events", "tickets": "tickets"},
    ),
}

# Account refs are masked before they leave the loader, as in the local gateway.
SELECT_OVERRIDES = {
    "merchants": (
        "SELECT id, name, CASE WHEN length(settlement_account_ref) <= 4 THEN '****' "
        "ELSE '******' || right(settlement_account_ref, 4) END AS settlement_account_ref FROM merchants"
    )
}


def _psql(database: str, sql: str) -> None:
    subprocess.run(["psql", *PG_ARGS, "-d", database, "-v", "ON_ERROR_STOP=1", "-q", "-c", sql], check=True)


def load() -> None:
    for database, (source_file, tables) in LAYOUT.items():
        exists = subprocess.run(
            ["psql", *PG_ARGS, "-d", "postgres", "-Atc", f"SELECT 1 FROM pg_database WHERE datname = '{database}'"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if not exists:
            _psql("postgres", f"CREATE DATABASE {database}")
        source = duckdb.connect(str(GENERATED / source_file), read_only=True)
        try:
            for source_table, target in tables.items():
                columns = source.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = ? ORDER BY ordinal_position",
                    [source_table],
                ).fetchall()
                ddl = ", ".join(f"{name} {PG_TYPES[kind]}" for name, kind in columns)
                # Drop the table, not the database: Zetaris keeps connections open to it.
                _psql(database, f"DROP TABLE IF EXISTS {target}")
                _psql(database, f"CREATE TABLE {target} ({ddl})")
                query = SELECT_OVERRIDES.get(source_table, f"SELECT * FROM {source_table}")
                with tempfile.TemporaryDirectory() as tmp:
                    csv_path = Path(tmp) / f"{target}.csv"
                    source.execute(f"COPY ({query}) TO '{csv_path.as_posix()}' (FORMAT CSV, HEADER)")
                    _psql(database, f"\\copy {target} FROM '{csv_path.as_posix()}' WITH (FORMAT csv, HEADER true)")
                count = source.execute(f"SELECT COUNT(*) FROM {source_table}").fetchone()[0]
                print(f"{database}.{target}: {count} rows")
        finally:
            source.close()


if __name__ == "__main__":
    load()
