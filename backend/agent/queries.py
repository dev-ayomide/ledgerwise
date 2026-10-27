"""Diagnostic SQL query functions for the investigation agent.

Each function returns a SQL string for DuckDB. All queries use schema-qualified
table names and pass guard_sql (single SELECT, allowed tables only).

Bank matched_reference values are messy (lower case, "REF/" prefix). Every join
normalises them with UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')).

Schema notes (from data/generate.py):
- processor.transactions: id, merchant_id, reference, amount_kobo, fee_kobo,
  currency, status, channel, created_at, updated_at, settlement_batch_id
- processor.ledger_entries: id, transaction_id, entry_type, amount_kobo, created_at
- processor.merchants: id, name, settlement_account_ref
- bank.settlement_lines: line_id, batch_ref, bank_reference, amount_kobo, value_date,
  narration, matched_reference
- bank.settlement_batches: batch_ref, total_kobo, line_count, cutoff_at
- events.webhook_events: id, transaction_reference, event_type, http_status, attempt,
  received_at, payload_hash
- support.tickets: id, merchant_id, transaction_reference, subject, body, created_at, status

WAT business date D:
  window_start = D-1 23:00:00 UTC
  window_end   = D    23:00:00 UTC
  cutoff       = D    20:00:00 UTC (bank batch cutoff)
"""

from __future__ import annotations

import datetime as dt
import re


def _window(day: str) -> tuple[str, str, str]:
    """Return (window_start, window_end, cutoff) as ISO strings for day D."""
    d = dt.date.fromisoformat(day)
    prev = d - dt.timedelta(days=1)
    window_start = f"{prev.isoformat()} 23:00:00"
    window_end = f"{d.isoformat()} 23:00:00"
    cutoff = f"{d.isoformat()} 20:00:00"
    return window_start, window_end, cutoff


def headline_gap(day: str) -> str:
    """Compute the headline gap for business date D.

    gap_kobo = SUM(processor success net) - SUM(bank line amount for value_date=D)
    """
    window_start, window_end, _ = _window(day)
    return f"""
WITH window_tx AS (
  SELECT id, amount_kobo, fee_kobo
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
),
expected AS (
  SELECT
    COALESCE(SUM(amount_kobo - fee_kobo), 0) AS expected_kobo,
    COUNT(*) AS success_count
  FROM window_tx
),
actual AS (
  SELECT
    COALESCE(SUM(amount_kobo), 0) AS actual_kobo,
    COUNT(*) AS line_count
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
),
hooks AS (
  SELECT COUNT(*) AS webhook_count
  FROM events.webhook_events
  WHERE received_at >= TIMESTAMP '{window_start}'
    AND received_at < TIMESTAMP '{window_end}'
),
tickets AS (
  SELECT COUNT(*) AS ticket_count
  FROM support.tickets
  WHERE created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
)
SELECT
  expected.expected_kobo,
  actual.actual_kobo,
  expected.expected_kobo - actual.actual_kobo AS gap_kobo,
  expected.success_count,
  actual.line_count,
  hooks.webhook_count,
  tickets.ticket_count
FROM expected, actual, hooks, tickets
""".strip()


def duplicate_webhooks(day: str) -> str:
    """Find matched_references with multiple processor success rows but fewer bank lines.

    Two processor.transactions share the same reference; bank paid only once
    (one settlement_line with matched_reference = that reference).
    Returns: reference, proc_count, bank_count, proc_net_kobo, bank_total_kobo, gap_kobo
    """
    window_start, window_end, _ = _window(day)
    return f"""
WITH proc_success AS (
  SELECT
    reference,
    COUNT(*) AS proc_count,
    SUM(amount_kobo - fee_kobo) AS proc_net_kobo
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
  GROUP BY reference
  HAVING COUNT(*) >= 2
),
bank_lines AS (
  SELECT
    UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference,
    COUNT(*) AS bank_count,
    COALESCE(SUM(amount_kobo), 0) AS bank_total_kobo
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
  GROUP BY UPPER(REGEXP_REPLACE(matched_reference, '^REF/', ''))
)
SELECT
  p.reference AS matched_reference,
  p.proc_count,
  COALESCE(b.bank_count, 0) AS bank_count,
  p.proc_net_kobo,
  COALESCE(b.bank_total_kobo, 0) AS bank_total_kobo,
  p.proc_net_kobo - COALESCE(b.bank_total_kobo, 0) AS gap_kobo
FROM proc_success p
LEFT JOIN bank_lines b
  ON b.matched_reference = p.reference
WHERE p.proc_count > COALESCE(b.bank_count, 0)
""".strip()


def cutoff_violations(day: str) -> str:
    """Find success transactions submitted after the 20:00 UTC bank cutoff.

    These have created_at in [D 20:00, D 23:00) but no bank line for value_date=D
    (the bank assigns them to the next value date instead). A later bank line
    must exist, which is the proof that the money arrived on another day.
    Returns: id, reference, amount_kobo, fee_kobo, net_kobo, created_at,
    later_value_date, later_line_id
    """
    window_start, window_end, cutoff = _window(day)
    return f"""
WITH after_cutoff AS (
  SELECT
    id,
    reference,
    amount_kobo,
    fee_kobo,
    amount_kobo - fee_kobo AS net_kobo,
    created_at
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{cutoff}'
    AND created_at < TIMESTAMP '{window_end}'
),
settled_today AS (
  SELECT DISTINCT UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
),
settled_later AS (
  SELECT
    UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference,
    MIN(value_date) AS later_value_date,
    MIN(line_id) AS later_line_id
  FROM bank.settlement_lines
  WHERE value_date > DATE '{day}'
  GROUP BY UPPER(REGEXP_REPLACE(matched_reference, '^REF/', ''))
)
SELECT
  ac.id,
  ac.reference,
  ac.amount_kobo,
  ac.fee_kobo,
  ac.net_kobo,
  ac.created_at,
  sl.later_value_date,
  sl.later_line_id
FROM after_cutoff ac
JOIN settled_later sl ON sl.matched_reference = ac.reference
WHERE ac.reference NOT IN (SELECT matched_reference FROM settled_today)
""".strip()


def fee_mismatches(day: str) -> str:
    """Find rows where bank line is short by a small fee discrepancy.

    Joins processor success transactions to bank lines on reference/matched_reference.
    The bank applied 250 bps while processor recorded 150 bps.
    Gap = proc_net - bank_amount, filtered to small gaps (<= 5% of net, integer arithmetic).
    Returns: matched_reference, proc_net, bank_amount, gap_kobo
    """
    window_start, window_end, _ = _window(day)
    return f"""
WITH proc_success AS (
  SELECT
    reference,
    amount_kobo - fee_kobo AS proc_net
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
),
bank_lines AS (
  SELECT
    UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference,
    SUM(amount_kobo) AS bank_amount
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
  GROUP BY UPPER(REGEXP_REPLACE(matched_reference, '^REF/', ''))
)
SELECT
  b.matched_reference,
  p.proc_net,
  b.bank_amount,
  p.proc_net - b.bank_amount AS gap_kobo
FROM proc_success p
JOIN bank_lines b
  ON b.matched_reference = p.reference
WHERE b.bank_amount < p.proc_net
  AND (p.proc_net - b.bank_amount) * 100 <= p.proc_net * 5
""".strip()


def partial_settlements(day: str) -> str:
    """Find success transactions with NO bank settlement line on any value date.

    The partial scenario in generate.py uses write_bank=False, meaning the processor
    has a success record with NO corresponding bank line — the full net is missing.
    Returns: reference, proc_net, gap_kobo
    """
    window_start, window_end, _ = _window(day)
    return f"""
WITH proc_success AS (
  SELECT
    reference,
    amount_kobo - fee_kobo AS proc_net
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
),
settled_refs AS (
  SELECT DISTINCT UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference
  FROM bank.settlement_lines
)
SELECT
  p.reference AS matched_reference,
  p.proc_net,
  p.proc_net AS bank_amount,
  p.proc_net AS gap_kobo
FROM proc_success p
WHERE p.reference NOT IN (SELECT matched_reference FROM settled_refs)
""".strip()


def stuck_pending(day: str) -> str:
    """Find bank lines for value_date=D whose matched_reference has no success in the window.

    The bank paid for a transaction that the processor still shows as pending.
    Returns: line_id, matched_reference, amount_kobo
    """
    window_start, window_end, _ = _window(day)
    return f"""
WITH bank_day AS (
  SELECT
    line_id,
    UPPER(REGEXP_REPLACE(matched_reference, '^REF/', '')) AS matched_reference,
    amount_kobo
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
),
proc_success_refs AS (
  SELECT DISTINCT reference
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '{window_start}'
    AND created_at < TIMESTAMP '{window_end}'
)
SELECT
  b.line_id,
  b.matched_reference,
  b.amount_kobo
FROM bank_day b
WHERE b.matched_reference NOT IN (SELECT reference FROM proc_success_refs)
  AND b.matched_reference IN (
    SELECT reference
    FROM processor.transactions
    WHERE status = 'pending'
      AND created_at >= TIMESTAMP '{window_start}'
      AND created_at < TIMESTAMP '{window_end}'
  )
""".strip()


def batch_header_gap(day: str) -> str:
    """Compare declared batch total vs sum of actual settlement lines.

    batch.total_kobo is the declared amount; SUM(lines.amount_kobo) is reality.
    header_gap_kobo = total_kobo - lines_total (positive if declared > actual).
    Returns: batch_ref, total_kobo, lines_total, header_gap_kobo
    """
    return f"""
WITH lines_sum AS (
  SELECT
    batch_ref,
    SUM(amount_kobo) AS lines_total
  FROM bank.settlement_lines
  WHERE value_date = DATE '{day}'
  GROUP BY batch_ref
)
SELECT
  b.batch_ref,
  b.total_kobo,
  COALESCE(ls.lines_total, 0) AS lines_total,
  b.total_kobo - COALESCE(ls.lines_total, 0) AS header_gap_kobo
FROM bank.settlement_batches b
LEFT JOIN lines_sum ls
  ON ls.batch_ref = b.batch_ref
WHERE b.batch_ref = 'batch_{day}'
""".strip()


# ---------------------------------------------------------------------------
# Falsification queries. Each one is designed to disprove a hypothesis.
# ---------------------------------------------------------------------------

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9/_\-]+$")


def _in_list(values: list[str]) -> str:
    """Quote identifiers that came back from the sources. Anything odd is refused."""
    cleaned = sorted({str(value) for value in values})
    if not cleaned:
        raise ValueError("Falsification needs at least one key.")
    for value in cleaned:
        if not _SAFE_VALUE.match(value):
            raise ValueError(f"Refusing to build SQL from unexpected key: {value!r}")
    return ", ".join(f"'{value}'" for value in cleaned)


def falsify_duplicate(refs: list[str]) -> str:
    """A real duplicate is a webhook retry: same reference, attempt number rising.

    If the two rows were distinct payments the webhook log would show one
    attempt each, not a retry sequence.
    """
    return f"""
SELECT
  transaction_reference,
  COUNT(*) AS events,
  COUNT(DISTINCT attempt) AS attempts,
  MIN(received_at) AS first_at,
  MAX(received_at) AS last_at
FROM events.webhook_events
WHERE transaction_reference IN ({_in_list(refs)})
  AND event_type = 'charge.success'
GROUP BY transaction_reference
""".strip()


def falsify_cutoff(line_ids: list[str]) -> str:
    """If the money really arrived on the later day, that bank line carries the full net."""
    return f"""
SELECT line_id, matched_reference, amount_kobo, value_date
FROM bank.settlement_lines
WHERE line_id IN ({_in_list(line_ids)})
""".strip()


def falsify_fee(refs: list[str]) -> str:
    """A fee mismatch is systematic: every short line implies the same extra rate."""
    return f"""
SELECT reference, amount_kobo, fee_kobo
FROM processor.transactions
WHERE reference IN ({_in_list(refs)})
""".strip()


def falsify_partial(amounts_kobo: list[int]) -> str:
    """Could the missing money sit in the bank file under a different reference?

    Only orphan lines count: lines with the same amount whose reference matches no
    processor transaction. A line with the same amount that belongs to another
    transaction is a coincidence, not the missing payment.
    """
    values = ", ".join(str(int(amount)) for amount in sorted(set(amounts_kobo)))
    return f"""
SELECT l.line_id, l.matched_reference, l.amount_kobo, l.value_date
FROM bank.settlement_lines l
WHERE l.amount_kobo IN ({values})
  AND UPPER(REGEXP_REPLACE(l.matched_reference, '^REF/', '')) NOT IN (
    SELECT reference FROM processor.transactions
  )
""".strip()


def falsify_stuck(refs: list[str]) -> str:
    """A stuck pending transaction shows server errors in the webhook log."""
    return f"""
SELECT transaction_reference, event_type, http_status, attempt
FROM events.webhook_events
WHERE transaction_reference IN ({_in_list(refs)})
""".strip()


def falsify_header(day: str) -> str:
    """Recount the batch from its lines instead of trusting the earlier sum."""
    return f"""
SELECT
  b.batch_ref,
  b.line_count AS declared_lines,
  b.total_kobo AS declared_total,
  COUNT(l.line_id) AS actual_lines,
  COALESCE(SUM(l.amount_kobo), 0) AS actual_total
FROM bank.settlement_batches b
LEFT JOIN bank.settlement_lines l ON l.batch_ref = b.batch_ref
WHERE b.batch_ref = 'batch_{day}'
GROUP BY b.batch_ref, b.line_count, b.total_kobo
""".strip()
