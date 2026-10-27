"""Demo CLI — runs the investigator and prints a formatted report.

Run as: .venv/bin/python -m backend.demo [--date YYYY-MM-DD] [--gateway local|zetaris]

Defaults: date=2026-10-21, gateway=local
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "data" / "generated"


def _fmt_ngn(kobo: int) -> str:
    """Format kobo amount as NGN with 2 decimal places, right-aligned in 15 chars."""
    ngn = kobo / 100
    return f"NGN {ngn:>15,.2f}"


def _build_gateway(gateway_name: str):
    """No silent fallback: asking for Zetaris and not getting it is an error."""
    if gateway_name == "zetaris":
        from backend.gateway.zetaris import ZetarisGateway
        from backend.settings import load_dotenv

        load_dotenv()
        gw = ZetarisGateway()
        gw._require_config()
        return gw, "zetaris-rest"

    if not (GENERATED_DIR / "processor.duckdb").exists():
        print("Generating synthetic data into data/generated/ …", file=sys.stderr)
        from data.generate import generate
        generate(GENERATED_DIR)

    from backend.gateway.local import LocalDuckDBGateway
    gw = LocalDuckDBGateway(GENERATED_DIR)
    return gw, "local-duckdb"


def _print_report(inv_result, gateway_label: str, elapsed_ms: int) -> None:
    from backend.agent.models import Investigation

    r: Investigation = inv_result

    w = 60  # inner box width

    def box_top(title: str = "") -> str:
        if title:
            pad = w - len(title) - 2
            left = pad // 2
            right = pad - left
            return f"╔{'═' * left} {title} {'═' * right}╗"
        return f"╔{'═' * w}╗"

    def box_bot() -> str:
        return f"╚{'═' * w}╝"

    def box_mid() -> str:
        return f"├{'─' * w}┤"

    def box_line(text: str = "") -> str:
        inner = f" {text}"
        pad = w - len(inner)
        return f"│{inner}{' ' * pad}│"

    # ── header ────────────────────────────────────────────────────────────────
    print(box_top("LEDGERWISE — SETTLEMENT INVESTIGATION"))
    print(box_bot())
    print()
    print(f"Question : {r.question}")
    print(f"Date     : {r.business_date}")
    print(f"Gateway  : {gateway_label}")
    print()

    # ── headline gap ──────────────────────────────────────────────────────────
    print(f"┌{'─' * w}┐")
    print(box_line("HEADLINE GAP"))
    print(box_mid())

    exp_str = _fmt_ngn(r.expected_kobo)
    act_str = _fmt_ngn(r.actual_kobo)
    gap_str = _fmt_ngn(abs(r.gap_kobo))

    exp_label = "Expected (processor net)"
    act_label = "Actual (bank lines)"
    gap_label = "Gap"

    print(box_line(f"  {exp_label:<26} {exp_str}"))
    print(box_line(f"  {act_label:<26} {act_str}"))
    print(box_line(f"  {gap_label:<26} {gap_str}  ←"))
    print(f"└{'─' * w}┘")
    print()

    # ── root causes ───────────────────────────────────────────────────────────
    n = len(r.root_causes)
    if n == 0:
        print(" ROOT CAUSES FOUND (0)")
        print(f" {'─' * w}")
        print("  None found.")
    else:
        print(f" ROOT CAUSES FOUND ({n})")
        print(f" {'─' * w}")
        for i, cause in enumerate(r.root_causes, 1):
            code_label = cause.code.replace("_", " ").title()
            amount_str = _fmt_ngn(cause.amount_kobo)
            print(f"  {i}. {cause.code:<25}  {amount_str}")
            # wrap summary to ~55 chars
            words = cause.summary.split()
            line_buf: list[str] = []
            lines: list[str] = []
            for word in words:
                line_buf.append(word)
                if len(" ".join(line_buf)) > 55:
                    lines.append(" ".join(line_buf[:-1]))
                    line_buf = [word]
            if line_buf:
                lines.append(" ".join(line_buf))
            for j, ln in enumerate(lines):
                if j == 0:
                    print(f"     {ln}")
                else:
                    print(f"     {ln}")
            print()

    print(f" {'─' * w}")

    # ── summary ───────────────────────────────────────────────────────────────
    explained = sum(c.amount_kobo for c in r.root_causes)
    explained_str = _fmt_ngn(explained)
    unexplained_str = _fmt_ngn(r.unexplained_kobo)

    print(f"  {'Explained':<12} {explained_str}")
    if r.unexplained_kobo == 0:
        print(f"  {'Unexplained':<12} {unexplained_str}  ✓ Fully reconciled")
    else:
        print(f"  {'Unexplained':<12} {unexplained_str}  ⚠ Not fully reconciled")

    print()
    print(f"Completed in {elapsed_ms}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ledgerwise settlement investigation demo")
    parser.add_argument(
        "--date",
        default="2026-10-21",
        metavar="YYYY-MM-DD",
        help="Business date to investigate (default: 2026-10-21)",
    )
    parser.add_argument(
        "--gateway",
        default="local",
        choices=["local", "zetaris"],
        help="Data gateway to use (default: local)",
    )
    args = parser.parse_args()

    gw, gateway_label = _build_gateway(args.gateway)

    from backend.agent.investigator import Investigator

    # Use the question from the demo scenario if date matches
    if args.date == "2026-10-21":
        question = "Why is NGN 4.2M missing from yesterday's settlement?"
    else:
        question = f"Why is there a settlement gap on {args.date}?"

    started = time.perf_counter()
    try:
        result = Investigator(gw).investigate(question, args.date)
    finally:
        gw.close()
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    _print_report(result, gateway_label, elapsed_ms)


if __name__ == "__main__":
    main()
