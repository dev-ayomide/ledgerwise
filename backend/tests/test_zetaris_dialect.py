"""Zetaris runs Spark SQL. The postgres rendering silently broke queries on the live platform."""

from backend.agent import queries
from backend.guard.sql_guard import guard_sql


def test_spark_rendering_has_no_postgres_only_syntax() -> None:
    for name in ("duplicate_webhooks", "cutoff_violations", "fee_mismatches", "partial_settlements", "stuck_pending"):
        sql = guard_sql(getattr(queries, name)("2026-10-21"), dialect="spark").sql
        assert "'g'" not in sql, name
        assert "DOUBLE PRECISION" not in sql, name
        assert "LIMIT 500" in sql


def test_falsifier_refuses_unexpected_keys() -> None:
    import pytest

    with pytest.raises(ValueError):
        queries.falsify_duplicate(["LW-1'; DROP TABLE x; --"])
