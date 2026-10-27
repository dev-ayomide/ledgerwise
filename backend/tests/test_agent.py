"""Tests for the investigation agent."""

from pathlib import Path

import pytest

from data.generate import generate
from backend.gateway.local import LocalDuckDBGateway
from backend.agent.investigator import Investigator


def _make(tmp_path: Path) -> tuple:
    data_dir = tmp_path / "sources"
    generate(data_dir)
    gw = LocalDuckDBGateway(data_dir)
    return gw, Investigator(gw)


def test_demo_all_four_causes(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate("Why is NGN 4.2M missing from yesterday's settlement?", "2026-10-21")
    finally:
        gw.close()
    assert result.gap_kobo == 420_000_000
    codes = {c.code for c in result.root_causes}
    assert "duplicate_webhook" in codes
    assert "cutoff_timezone" in codes
    assert "partial_settlement" in codes
    assert "fee_mismatch" in codes
    assert result.unexplained_kobo == 0


def test_single_duplicate(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate("Why is the 14 October 2026 settlement short?", "2026-10-14")
    finally:
        gw.close()
    assert result.gap_kobo == 25_000_000
    codes = {c.code for c in result.root_causes}
    assert "duplicate_webhook" in codes
    assert result.unexplained_kobo == 0


def test_single_cutoff(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate(
            "Why are transfers missing from the 17 October settlement?", "2026-10-17"
        )
    finally:
        gw.close()
    assert result.gap_kobo > 0
    codes = {c.code for c in result.root_causes}
    assert "cutoff_timezone" in codes
    assert result.unexplained_kobo == 0


def test_single_fee_mismatch(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate("Why is the 16 October settlement short?", "2026-10-16")
    finally:
        gw.close()
    assert result.gap_kobo > 0
    codes = {c.code for c in result.root_causes}
    assert "fee_mismatch" in codes
    assert result.unexplained_kobo == 0


def test_single_partial(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate("Why is the 19 October settlement short?", "2026-10-19")
    finally:
        gw.close()
    assert result.gap_kobo > 0
    codes = {c.code for c in result.root_causes}
    assert "partial_settlement" in codes
    assert result.unexplained_kobo == 0


def test_stuck_pending(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate(
            "Why did the bank settle more than our ledger on 15 October?", "2026-10-15"
        )
    finally:
        gw.close()
    assert result.gap_kobo < 0  # bank paid more
    codes = {c.code for c in result.root_causes}
    assert "stuck_pending" in codes
    assert result.unexplained_kobo == 0


def test_red_herring(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate("Is the 20 October settlement correct?", "2026-10-20")
    finally:
        gw.close()
    # Red herring: gap is 0, no root causes from lines, possibly a header discrepancy
    assert result.gap_kobo == 0


def test_unexplained_header(tmp_path: Path) -> None:
    gw, inv = _make(tmp_path)
    try:
        result = inv.investigate(
            "The 13 October 2026 batch header is NGN 50,000 below the settlement lines. "
            "What explains it?",
            "2026-10-13",
        )
    finally:
        gw.close()
    assert result.gap_kobo == 0
    codes = {c.code for c in result.root_causes}
    assert "header_discrepancy" in codes


def test_injection_ticket_changes_nothing(tmp_path: Path) -> None:
    """A ticket body that says DELETE must neither run nor leak into any agent query."""
    gw, inv = _make(tmp_path)
    try:
        before = gw.query("SELECT COUNT(*) AS n FROM processor.transactions").rows[0]["n"]
        result = inv.investigate("Is the 20 October settlement correct?", "2026-10-20")
        after = gw.query("SELECT COUNT(*) AS n FROM processor.transactions").rows[0]["n"]
        statements = [e["sql"] for e in inv.last_run.evidence.values()]
    finally:
        gw.close()
    assert before == after
    assert result.root_causes == []
    assert not any("DELETE" in sql.upper() for sql in statements)
