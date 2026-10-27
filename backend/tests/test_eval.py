"""Smoke test for the eval harness.

Generates synthetic data in a temp directory and runs evaluate_all(),
asserting every scenario scores 100.
"""

from pathlib import Path

import pytest

from data.generate import generate
from backend.eval import evaluate_all


def test_all_scenarios_score_100(tmp_path: Path) -> None:
    data_dir = tmp_path / "sources"
    generate(data_dir)
    results = evaluate_all(data_dir)
    for r in results:
        assert r["score"] == 100, f"{r['scenario_id']} scored {r['score']}: {r}"
