# Architecture

```
Browser (plain HTML/JS)  <--SSE-->  FastAPI (backend/app/main.py)
                                          |
                                   Investigator (backend/agent)
                                   detect -> falsify -> reconcile (code) -> report -> propose
                                          |                         \
                                    SQL guard                     Narrative (optional LLM,
                                          |                       validated, template fallback)
                                    DataGateway
                          +---------------+----------------+
                    ZetarisGateway                 LocalDuckDBGateway
                  (REST, Spark SQL)                 (tests only)
                          |
        +-----------------+------------------+
   processor (Postgres)  events+support (Postgres)  bank (Parquet files)
   transactions          webhook_events, tickets     settlement_lines
   ledger_entries                                    settlement_batches
   merchants (masked)
```

## Investigation flow

1. `understand`: one federated query returns expected processor net, bank lines, gap, webhook and ticket counts (it touches all four logical sources).
2. `plan`: the checks to run depend on the sign of the gap. Gap above zero: missing bank line, cutoff, duplicate webhook, fee mismatch. Gap below zero: stuck pending. Gap zero: batch header.
3. `investigate` and `hypothesize`: one detector query per check. A hit becomes a hypothesis with an amount and an evidence id.
4. `falsify`: a second query per hypothesis built to disprove it (webhook retry sequence, later bank line equals net, constant rate difference, no orphan line with that amount, server errors in the webhook log, recount of the batch). A hypothesis that fails is dropped and listed.
5. `reconcile_math`: explained and unexplained amounts are computed in Python.
6. `conclude`: structured report. Confidence is derived: high needs a surviving falsification, evidence rows, and zero unexplained; medium if a remainder exists; low otherwise.
7. `propose_actions`: drafts only. Approving writes a draft document to `data/investigations/`. Nothing is executed.

## Guardrails

- SQL guard (sqlglot): one SELECT, tables on an allowlist, schema-qualified, LIMIT capped at 500, no file-reading functions, no `SELECT *` on `processor.merchants`.
- Falsifier SQL is built only from keys read back from the sources and refuses anything outside `[A-Za-z0-9/_-]`.
- Ticket bodies and narrations are never put into a query or a prompt. The red-herring days contain a ticket that says to run DELETE; a test checks nothing changes and no agent query contains it.
- Amounts are integer kobo end to end. Formatting to NGN happens only in `narrative.fmt_ngn` and the UI.
- Account references are masked when loaded into Postgres.
- Every query is stored with its SQL, sources, row count, duration and rows (first 50) as an evidence record. Each investigation is saved as JSON and can be replayed.

## Where models are used

- NVIDIA Nemotron: the plain-language summary, only when `NVIDIA_API_KEY`, `NVIDIA_BASE_URL` and `NEMOTRON_MODEL` are set. Output is validated against the facts. Not configured at the time of writing.
- Meterless: not integrated. See README.
