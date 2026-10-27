"""The falsifier must be able to drop a hypothesis, not only confirm it."""

from pathlib import Path

from backend.agent.investigator import Investigator
from backend.gateway.local import LocalDuckDBGateway
from data.generate import generate


class _NoRetryLog:
    """Wraps a gateway and hides webhook retries, as if the log showed two distinct payments."""

    def __init__(self, inner) -> None:
        self.inner = inner

    def query(self, sql: str):
        result = self.inner.query(sql)
        if "FROM events.webhook_events" in result.sql and "GROUP BY transaction_reference" in result.sql:
            for row in result.rows:
                row["attempts"] = 1
        return result


def test_duplicate_is_dropped_when_log_shows_no_retry(tmp_path: Path) -> None:
    data_dir = tmp_path / "sources"
    generate(data_dir)
    gateway = LocalDuckDBGateway(data_dir)
    try:
        result = Investigator(_NoRetryLog(gateway)).investigate("q", "2026-10-14")
    finally:
        gateway.close()
    assert result.root_causes == []
    assert [d["code"] for d in result.dropped] == ["duplicate_webhook"]
    # the amount is not silently counted: it shows up as unexplained
    assert result.unexplained_kobo == 25_000_000


def test_every_kept_cause_survived_and_has_evidence(tmp_path: Path) -> None:
    data_dir = tmp_path / "sources"
    generate(data_dir)
    gateway = LocalDuckDBGateway(data_dir)
    try:
        inv = Investigator(gateway)
        result = inv.investigate("q", "2026-10-21")
        known = set(inv.last_run.evidence)
    finally:
        gateway.close()
    for cause in result.root_causes:
        assert cause.survived_falsification is True
        assert cause.confidence == "high"
        assert len(cause.evidence_ids) >= 2  # the finding query and the falsification query
        assert set(cause.evidence_ids) <= known
