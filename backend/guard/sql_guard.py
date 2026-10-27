"""Reject anything that is not one read-only query against the allowlist.

The agent never writes to a source. Ticket bodies and bank narrations are
untrusted, so text that looks like a second statement or a destructive
command must fail here before it reaches DuckDB or Zetaris.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

MAX_LIMIT = 500

ALLOWED_TABLES = frozenset(
    {
        "processor.transactions",
        "processor.ledger_entries",
        "processor.merchants",
        "bank.settlement_lines",
        "bank.settlement_batches",
        "events.webhook_events",
        "support.tickets",
    }
)

# SELECT * would return the raw settlement account. The view also masks it.
MASKED_TABLES = frozenset({"processor.merchants"})

READ_TYPES = (exp.Select, exp.Union, exp.Except, exp.Intersect)

FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.Copy,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Revoke,
)

DENIED_FUNCTIONS = frozenset(
    {
        "read_parquet",
        "read_csv",
        "read_csv_auto",
        "read_json",
        "read_blob",
        "glob",
        "sqlite_scan",
        "postgres_scan",
        "iceberg_scan",
        "delta_scan",
        "load_extension",
        "current_setting",
        "getenv",
        "query",
        "query_table",
    }
)


class SqlGuardError(ValueError):
    """The statement is not a single allowlisted read."""


@dataclass(frozen=True)
class GuardedSQL:
    sql: str
    tables: frozenset[str]


def guard_sql(sql: str, *, dialect: str = "duckdb") -> GuardedSQL:
    """Validate `sql` and return a single statement with a bounded LIMIT."""

    if not sql or not sql.strip():
        raise SqlGuardError("SQL is empty.")
    if "\x00" in sql:
        raise SqlGuardError("SQL contains a null byte.")

    try:
        parsed = [statement for statement in sqlglot.parse(sql) if statement is not None]
    except ParseError as error:
        raise SqlGuardError("SQL could not be parsed as one read query.") from error

    if len(parsed) != 1:
        raise SqlGuardError("Only one statement is allowed.")

    statement = parsed[0]
    if not isinstance(statement, READ_TYPES):
        raise SqlGuardError("Only a single SELECT is allowed.")

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_TYPES):
            raise SqlGuardError("Only a single SELECT is allowed.")
        function_name = _function_name(node)
        if function_name in DENIED_FUNCTIONS:
            raise SqlGuardError(f"Function {function_name} is not allowed.")

    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        qualified = _qualify(table)
        if qualified is None:
            if table.name in cte_names:
                continue
            raise SqlGuardError("Tables must be schema-qualified.")
        if qualified not in ALLOWED_TABLES:
            raise SqlGuardError(f"Table {qualified} is not allowed.")
        tables.add(qualified)

    for select in statement.find_all(exp.Select):
        if _selects_star(select) and _direct_tables(select) & MASKED_TABLES:
            raise SqlGuardError(
                "SELECT * is not allowed on processor.merchants."
            )

    _cap_limit(statement)
    rendered = statement.sql(dialect=dialect)
    return GuardedSQL(sql=rendered, tables=frozenset(tables))


def _qualify(table: exp.Table) -> str | None:
    if table.catalog:
        return None
    if not table.db or not table.name:
        return None
    return f"{table.db}.{table.name}"


def _selects_star(select: exp.Select) -> bool:
    for expression in select.args.get("expressions") or []:
        if isinstance(expression, exp.Star):
            return True
        if isinstance(expression, exp.Column) and isinstance(expression.this, exp.Star):
            return True
    return False


def _direct_tables(select: exp.Select) -> set[str]:
    sources = []
    from_clause = select.args.get("from_")
    if from_clause is None:
        from_clause = select.args.get("from")
    if from_clause is not None:
        sources.append(from_clause)
    sources.extend(select.args.get("joins") or [])
    names: set[str] = set()
    for source in sources:
        for table in source.find_all(exp.Table):
            qualified = _qualify(table)
            if qualified:
                names.add(qualified)
    return names


def _function_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return (node.name or "").lower()
    if isinstance(node, exp.Func):
        sql_name = getattr(node, "sql_name", None)
        if callable(sql_name):
            return str(sql_name()).lower()
    return ""


def _cap_limit(statement: exp.Expression) -> None:
    current = statement.args.get("limit")
    if current is None:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(MAX_LIMIT)))
        return
    value = current.args.get("expression")
    if not isinstance(value, exp.Literal) or not value.is_int:
        raise SqlGuardError("LIMIT must be a positive integer.")
    number = int(value.this)
    if number < 1:
        raise SqlGuardError("LIMIT must be a positive integer.")
    if number > MAX_LIMIT:
        current.set("expression", exp.Literal.number(MAX_LIMIT))
