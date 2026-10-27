"""Eval harness — scores Investigator output against ground_truth.json.

Run as: .venv/bin/python -m backend.eval
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_ground_truth() -> list[dict]:
    path = ROOT / "data" / "ground_truth.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data["scenarios"]


def _score_scenario(scenario: dict, inv) -> dict:
    """Run the investigator against one scenario and return a score dict."""
    from backend.agent.investigator import Investigator

    question = scenario["question"]
    business_date = scenario["business_date"]
    expected_gap = scenario["line_gap_kobo"]
    expected_causes: list[dict] = scenario.get("root_causes", [])
    expected_unexplained = scenario.get("unexplained_kobo", 0)
    scenario_id = scenario["id"]

    result = inv.investigate(question, business_date)

    # ── gap_correct ──────────────────────────────────────────────────────────
    gap_correct = abs(result.gap_kobo - expected_gap) <= 1

    # ── special case: unexplained-header ──────────────────────────────────────
    # line_gap == 0, root_causes == [], unexplained_kobo == 5000000
    # We score as perfect if investigator found 'header_discrepancy' with
    # amount == expected_unexplained (5000000).
    is_header_scenario = (
        expected_gap == 0
        and not expected_causes
        and expected_unexplained != 0
    )

    # ── special case: red-herring ────────────────────────────────────────────
    is_red_herring = scenario.get("red_herring", False)

    found_codes = {rc.code for rc in result.root_causes}
    expected_codes = {c["code"] for c in expected_causes}

    # ── causes_found ─────────────────────────────────────────────────────────
    causes_found = found_codes == expected_codes

    # ── amounts_correct ───────────────────────────────────────────────────────
    amounts_correct = True
    expected_by_code = {c["code"]: c["amount_kobo"] for c in expected_causes}
    for rc in result.root_causes:
        if rc.code in expected_by_code:
            if abs(rc.amount_kobo - expected_by_code[rc.code]) > 1:
                amounts_correct = False
                break

    # ── unexplained_correct ──────────────────────────────────────────────────
    unexplained_correct = result.unexplained_kobo == expected_unexplained

    # ── override scoring for header scenario ─────────────────────────────────
    if is_header_scenario:
        hd_causes = [rc for rc in result.root_causes if rc.code == "header_discrepancy"]
        if hd_causes and abs(hd_causes[0].amount_kobo - expected_unexplained) <= 1:
            # Perfect: found the header discrepancy with the right amount
            causes_found = True
            amounts_correct = True
            unexplained_correct = True
            gap_correct = True  # line gap == 0, result.gap_kobo should also be 0
        else:
            # Didn't identify it
            causes_found = False

    # ── override scoring for red-herring ─────────────────────────────────────
    if is_red_herring:
        # Perfect if unexplained == 0 and no false positive causes
        causes_found = len(result.root_causes) == 0
        amounts_correct = True
        unexplained_correct = result.unexplained_kobo == 0
        # line_gap is 0, expected result.gap_kobo == 0
        gap_correct = result.gap_kobo == 0

    # ── compute score ─────────────────────────────────────────────────────────
    score = 100

    if not gap_correct:
        score -= 10
    if not unexplained_correct:
        score -= 10

    if is_header_scenario:
        # Causes: just one cause (header_discrepancy) — either found or not
        if not causes_found:
            score -= 25
        if not amounts_correct:
            score -= 25
    elif is_red_herring:
        # False positive causes
        false_positives = len(result.root_causes)
        score -= false_positives * 25
    else:
        # Wrong cause codes identified (false positives)
        wrong = found_codes - expected_codes
        score -= len(wrong) * 25
        # Missing expected causes
        missing = expected_codes - found_codes
        score -= len(missing) * 25
        if not amounts_correct:
            score -= 25

    score = max(0, score)

    return {
        "scenario_id": scenario_id,
        "gap_correct": gap_correct,
        "causes_found": causes_found,
        "amounts_correct": amounts_correct,
        "unexplained_correct": unexplained_correct,
        "held_out": bool(scenario.get("held_out", False)),
        "score": score,
        "gap_kobo": result.gap_kobo,
        "expected_gap_kobo": expected_gap,
        "found_codes": sorted(found_codes),
        "expected_codes": sorted(expected_codes),
        "unexplained_kobo": result.unexplained_kobo,
        "expected_unexplained_kobo": expected_unexplained,
    }


def evaluate_all(data_dir: Path) -> list[dict]:
    """Public function: generate data at data_dir, run all scenarios, return score dicts."""
    from backend.gateway.local import LocalDuckDBGateway
    from backend.agent.investigator import Investigator

    scenarios = _load_ground_truth()
    gw = LocalDuckDBGateway(data_dir)
    try:
        inv = Investigator(gw)
        results = []
        for scenario in scenarios:
            result = _score_scenario(scenario, inv)
            results.append(result)
    finally:
        gw.close()
    return results


def _print_table(results: list[dict]) -> None:
    col_w = 36
    header = f"{'Scenario':<{col_w}} {'gap':<5} {'causes':<8} {'amounts':<9} {'unexplained':<13} {'score':>5}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for r in results:
        gap = "✓" if r["gap_correct"] else "✗"
        causes = "✓" if r["causes_found"] else "✗"
        amounts = "✓" if r["amounts_correct"] else "✗"
        unexpl = "✓" if r["unexplained_correct"] else "✗"
        score = r["score"]
        sid = r["scenario_id"]
        if len(sid) > col_w - 1:
            sid = sid[: col_w - 4] + "..."
        print(f"{sid:<{col_w}} {gap:<5} {causes:<8} {amounts:<9} {unexpl:<13} {score:>5}")
    print(sep)
    total = sum(r["score"] for r in results)
    max_total = 100 * len(results)
    print(f"{'OVERALL':<{col_w + 5 + 8 + 9 + 13}} {total}/{max_total}")


def _write_results(results: list[dict], engine: str, seconds: float) -> None:
    import datetime as dt

    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    total = sum(r["score"] for r in results)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload = {
        "run_at": stamp,
        "engine": engine,
        "scenarios": len(results),
        "score": total,
        "max_score": 100 * len(results),
        "seconds": round(seconds, 1),
        "results": results,
    }
    (out / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        f"# Eval results ({engine})",
        "",
        f"Run at {stamp}. {len(results)} scenarios, {total}/{100 * len(results)} points, {round(seconds, 1)} s.",
        "",
        "| Scenario | Gap | Causes | Amounts | Unexplained | Score |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        mark = lambda ok: "pass" if ok else "FAIL"  # noqa: E731
        lines.append(
            f"| {r['scenario_id']} | {mark(r['gap_correct'])} | {mark(r['causes_found'])} | "
            f"{mark(r['amounts_correct'])} | {mark(r['unexplained_correct'])} | {r['score']} |"
        )
    (out / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    import argparse
    import time

    from backend.agent.investigator import Investigator
    from data.generate import generate

    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", choices=["local", "zetaris"], default="local")
    args = parser.parse_args()
    scenarios = _load_ground_truth()
    started = time.perf_counter()

    if args.gateway == "zetaris":
        from backend.gateway.zetaris import ZetarisGateway

        gw = ZetarisGateway()
        inv = Investigator(gw)
        results = [_score_scenario(scenario, inv) for scenario in scenarios]
        engine = "zetaris-rest"
    else:
        from backend.gateway.local import LocalDuckDBGateway

        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "sources"
            generate(data_dir)
            gw = LocalDuckDBGateway(data_dir)
            try:
                inv = Investigator(gw)
                results = [_score_scenario(scenario, inv) for scenario in scenarios]
            finally:
                gw.close()
        engine = "local-duckdb"

    _print_table(results)
    _write_results(results, engine, time.perf_counter() - started)
    all_perfect = all(r["score"] == 100 for r in results)
    sys.exit(0 if all_perfect else 1)


if __name__ == "__main__":
    main()
