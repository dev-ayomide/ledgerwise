"""Run the headline cross-source query on the local gateway.

This proves the three files can be joined. It does not prove Zetaris.
"""

from __future__ import annotations

from pathlib import Path

from backend.gateway.local import LocalDuckDBGateway
from data.generate import DEMO_DATE, ROOT, generate


def main() -> None:
    out = ROOT / "data" / "generated"
    generate(out, write_canonical_truth=True)
    sql = (ROOT / "data" / "queries" / "headline_gap.sql").read_text(encoding="utf-8")
    gateway = LocalDuckDBGateway(out)
    try:
        result = gateway.query(sql)
    finally:
        gateway.close()
    row = result.rows[0]
    gap = int(row["gap_kobo"])
    naira = gap / 100
    print(f"Business date {DEMO_DATE.isoformat()} (treated as yesterday on 22 Oct 2026)")
    print(f"Engine {result.engine}")
    print(f"Tables {', '.join(result.tables)}")
    print(f"Expected kobo {row['expected_kobo']}")
    print(f"Bank lines kobo {row['actual_kobo']}")
    print(f"Gap kobo {gap} (NGN {naira:,.0f})")
    print(f"Webhooks in window {row['webhook_count']}, tickets {row['ticket_count']}")
    if gap != 420_000_000:
        raise SystemExit(f"Expected gap 420000000 kobo, got {gap}.")


if __name__ == "__main__":
    main()
