-- One read-only query across processor, bank files, and the events database.
-- Business date 21 Oct 2026 is West Africa Time: [20 Oct 23:00 UTC, 21 Oct 23:00 UTC).
-- gap_kobo = successful processor net minus bank lines dated that day.
WITH window_tx AS (
  SELECT id, amount_kobo, fee_kobo
  FROM processor.transactions
  WHERE status = 'success'
    AND created_at >= TIMESTAMP '2026-10-20 23:00:00'
    AND created_at < TIMESTAMP '2026-10-21 23:00:00'
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
  WHERE value_date = DATE '2026-10-21'
),
hooks AS (
  SELECT COUNT(*) AS webhook_count
  FROM events.webhook_events
  WHERE received_at >= TIMESTAMP '2026-10-20 23:00:00'
    AND received_at < TIMESTAMP '2026-10-21 23:00:00'
),
tickets AS (
  SELECT COUNT(*) AS ticket_count
  FROM support.tickets
  WHERE created_at >= TIMESTAMP '2026-10-20 23:00:00'
    AND created_at < TIMESTAMP '2026-10-21 23:00:00'
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
