"""Register the Ledgerwise sources in a local Zetaris platform.

These are the statements that were run by hand on 27 Oct 2026, in order:

1. Postgres databases ledgerwise_processor and ledgerwise_events (data/load_postgres.py).
2. CREATE DATASOURCE for processor, events and support (JDBC, host.docker.internal:5432).
3. REGISTER DATASOURCE TABLE(S) so the tables become queryable as <source>.<table>.
4. Copy the bank Parquet files into the driver container's shared file root.
5. CREATE LIGHTNING DATABASE bank and one FILESTORE TABLE per Parquet file.

Zetaris cannot read DuckDB files, which is why the processor and events sources
are Postgres here. Run once; existing sources are skipped.

    .venv/bin/python -m data.load_postgres
    .venv/bin/python -m infra.register_zetaris
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import httpx

from backend.settings import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get("ZETARIS_DRIVER_CONTAINER", "zetaris-driver-1")
SHARED = "/home/zetaris/customer-data/shared/ledgerwise_bank"
PG_HOST = os.environ.get("LEDGERWISE_PG_URL_HOST", "host.docker.internal")
PG_USER = os.environ.get("LEDGERWISE_PG_USER", os.environ.get("USER", "postgres"))


def run(sql: str) -> list[list[str]]:
    base = os.environ["ZETARIS_REST_URL"]
    response = httpx.post(
        f"{base}/sql-editor/sqls/run",
        json={"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": 100},
        headers={
            "Authorization": f"Bearer {os.environ['ZETARIS_API_KEY']}",
            "X-Org-ID": os.environ["ZETARIS_ORG_ID"],
            "X-Request-ID": str(uuid.uuid4()),
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise SystemExit(f"{sql[:70]}...\n  -> {response.status_code} {response.text[:300]}")
    return response.json().get("data", [])


def datasource(name: str, database: str) -> str:
    return (
        f'CREATE DATASOURCE {name} DESCRIBE BY "Ledgerwise_{name}_Postgres" OPTIONS ('
        'jdbcdriver "org.postgresql.Driver", '
        f'jdbcurl "jdbc:postgresql://{PG_HOST}:5432/{database}", '
        f'username "{PG_USER}", password "unused", fetchsize "1000")'
    )


def main() -> None:
    load_dotenv()
    have = {row[0] for row in run("SHOW DATASOURCES")}
    plan = [
        ("processor", "ledgerwise_processor", 'REGISTER DATASOURCE TABLES FROM processor'),
        ("events", "ledgerwise_events", 'REGISTER DATASOURCE TABLE "webhook_events" FROM events'),
        ("support", "ledgerwise_events", 'REGISTER DATASOURCE TABLE "tickets" FROM support'),
    ]
    for name, database, register in plan:
        if name in have:
            print(f"datasource {name}: exists, skipped")
            continue
        run(datasource(name, database))
        run(register)
        print(f"datasource {name}: created and tables registered")

    databases = {row[0] for row in run("SHOW LIGHTNING DATABASES")}
    if "bank" in databases:
        print("bank: exists, skipped")
        return
    subprocess.run(["docker", "exec", "-u", "0", CONTAINER, "mkdir", "-p", SHARED], check=True)
    for name in ("settlement_lines", "settlement_batches"):
        source = ROOT / "data" / "generated" / "bank" / f"{name}.parquet"
        subprocess.run(["docker", "cp", str(source), f"{CONTAINER}:{SHARED}/{name}.parquet"], check=True)
    subprocess.run(
        ["docker", "exec", "-u", "0", CONTAINER, "sh", "-c", f"chown -R zetaris:zetaris {SHARED} && chmod -R g+w {SHARED}"],
        check=True,
    )
    run('CREATE LIGHTNING DATABASE bank DESCRIBE BY "Ledgerwise_bank_settlement_files"')
    for name in ("settlement_lines", "settlement_batches"):
        run(
            f"CREATE LIGHTNING FILESTORE TABLE {name} FROM bank FORMAT PARQUET "
            f'OPTIONS (PATH "{SHARED}/{name}.parquet", inferSchema "true")'
        )
    print("bank: created with settlement_lines and settlement_batches")


if __name__ == "__main__":
    main()
