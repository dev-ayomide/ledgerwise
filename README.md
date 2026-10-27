# Ledgerwise

Ledgerwise investigates payment settlement gaps. A finance operations analyst asks "Why is NGN 4.2M missing from yesterday's settlement?" and Ledgerwise queries the processor database, the webhook log, support tickets and the bank settlement files through one federated SQL layer (Zetaris). It proposes causes, tries to disprove each one with a second query, computes the amounts in code, and returns a report where every claim points at the exact query and rows behind it. It only reads. Fixes are drafts that a person approves.

Track 02, "The Agent That Can Explain Why". All data is synthetic.

## What you see

1. A settlement dashboard with flagged gaps per value date (live queries through Zetaris).
2. A live investigation timeline: plan, each query with the sources it touched, findings, hypotheses, a falsification attempt for each, the reconciliation.
3. An evidence panel. Click any evidence id to see the SQL and the rows.
4. A report: gap by cause, unexplained remainder, confidence per cause, proposed actions with Approve and Reject. Approving creates a draft. Nothing is sent or executed.
5. Markdown export and replay of any past investigation.

## Demo case

21 October 2026 is short by NGN 4,200,000 (420,000,000 kobo). Ledgerwise finds four causes and an unexplained remainder of zero:

| Cause | Amount (kobo) | How it was challenged |
|---|---|---|
| A successful ledger credit with no bank line | 180,000,000 | No unmatched bank line anywhere carries that amount |
| Three transfers after the 20:00 UTC bank cutoff, paid the next day | 150,000,000 | The later bank lines equal the processor net exactly |
| A retried webhook that created a second credit | 70,000,000 | The webhook log shows attempt 1 then attempt 2 for the reference |
| Fee 150 bps at the processor, 250 bps at the bank, 20 lines | 20,000,000 | Every short line is off by the same 100 bps |

## Architecture

```
Browser (HTML/JS) <--SSE--> FastAPI --> Investigator --> SQL guard --> DataGateway
                                                                          |
                                                          ZetarisGateway (REST, Spark SQL)
                                                                          |
                              processor (Postgres)   events + support (Postgres)   bank (Parquet)
```

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Agent steps: understand, plan, investigate, hypothesize, falsify, reconcile (in code), conclude, propose actions.

## How Zetaris is used

Everything the agent reads goes through Zetaris Lightning SQL on the local hackathon platform. The processor and events/support data are two Postgres databases registered with `CREATE DATASOURCE`. The bank settlement files are Parquet, registered with `CREATE LIGHTNING FILESTORE TABLE`. The first query of every investigation is one statement that joins all four logical sources. Every query is validated by the SQL guard first, then rendered as Spark SQL for Zetaris. Reproduce the setup with `data/load_postgres.py` and `infra/register_zetaris.py`. Verified syntax and quirks are in [docs/SPONSOR_NOTES.md](docs/SPONSOR_NOTES.md).

Not used: Zetaris masking policies (account references are masked in the loader instead), MCP, AgentFlow.

## How NVIDIA Nemotron is used

Status: not integrated yet. The code path exists (`backend/llm/client.py`, `backend/agent/narrative.py`): when `NVIDIA_API_KEY`, `NVIDIA_BASE_URL` and `NEMOTRON_MODEL` are set, the model writes the plain-language summary from the structured report, and its output is rejected if it cites an unknown evidence id or contains a number that is not in the facts. Without those variables a deterministic template writes the summary, and the UI labels which one ran. No model id has been confirmed in this repo.

## How Meterless is used

Status: not integrated. No hackathon endpoint or installer path was available to this team, and a local JSON file is not Meterless. See [docs/SPONSOR_NOTES.md](docs/SPONSOR_NOTES.md) for what is publicly documented.

## How Cursor is used

See [docs/BUILT_WITH_CURSOR.md](docs/BUILT_WITH_CURSOR.md).

## Safety

- SQL guard: one SELECT, allowlisted schema-qualified tables, LIMIT capped at 500, file-reading functions denied, no `SELECT *` on the masked table. Tested, including a ticket body that says `DELETE FROM processor.transactions`.
- Ticket text and narrations never enter a query or a prompt. A test checks that the injection ticket changes nothing and appears in no agent query.
- Amounts are integer kobo. The model never produces or changes a number.
- The agent proposes. People approve. Approved actions are draft text files.

## Run it

Prerequisites: Python 3.11+, the Zetaris hackathon platform running locally, Postgres on 127.0.0.1:5432, Docker.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env.local        # then fill in the Zetaris values
.venv/bin/python -m data.generate          # synthetic data and ground truth
.venv/bin/python -m data.load_postgres     # creates ledgerwise_processor and ledgerwise_events
.venv/bin/python -m infra.register_zetaris # registers the sources in Zetaris
LEDGERWISE_GATEWAY=zetaris .venv/bin/uvicorn backend.app.main:app --port 8765
```

Open http://localhost:8765. Without Zetaris, `LEDGERWISE_GATEWAY=local` runs the DuckDB test double; the UI badge says so. There is no silent fallback.

```bash
.venv/bin/pytest                                   # 36 tests
.venv/bin/python -m backend.eval --gateway zetaris # 21 scenarios, live
.venv/bin/python -m backend.demo                   # terminal version
```

## Evaluation (measured)

21 scenarios: 8 original, 8 two- and three-fault combinations, 3 red herrings, 2 with an unattributable short payment that must be reported as unexplained. Score on live Zetaris: **2100/2100**. The first run on the 13 new scenarios scored 1995/2100 before a falsifier bug was fixed; the log has the failures and the fix. Five scenarios were held out and passed on the first run. Details and what this does not show: [docs/EVAL_LOG.md](docs/EVAL_LOG.md).

## Limitations

- The investigation logic is deterministic rules plus falsification queries. It is not an LLM deciding what to look at. A perfect score on synthetic scenarios from the same author shows the rules match the injected faults, not that they generalise to real data.
- Six causes are covered: duplicate webhook, cutoff/timezone, fee mismatch, partial settlement, stuck pending, header discrepancy. Reversal without ledger entry, rounding, duplicate bank lines, missing-webhook tickets and chargebacks are not implemented.
- A short payment under 5% of net would be labelled a fee mismatch. Not tested.
- No public deployment. Zetaris runs locally, so the demo is a local run and the recorded video.
- Nemotron and Meterless are not integrated (see above).
- No authentication. Synthetic data only.
