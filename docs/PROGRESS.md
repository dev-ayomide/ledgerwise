# Progress

## 2026-10-27 — Investigation agent loop

Done:

- `backend/agent/models.py` — `RootCause` and `Investigation` Pydantic models.
- `backend/agent/queries.py` — 7 diagnostic SQL functions (headline gap, duplicate webhooks, cutoff violations, fee mismatches, partial settlements, stuck pending, batch header gap). Schema corrections discovered during testing: `processor.transactions` uses `reference` not `matched_reference`; `bank.settlement_lines` uses `line_id` and `batch_ref`; `bank.settlement_batches` uses `batch_ref` and `total_kobo`; partial settlement uses `write_bank=False` (no bank line at all, not a half-paid line).
- `backend/agent/investigator.py` — Rule-based multi-step agent loop. Runs the headline query, then branches by sign of gap_kobo: positive gap → duplicate, cutoff, fee mismatch, partial; negative gap → stuck pending; zero gap → batch header check. Returns a structured `Investigation`.
- `backend/tests/test_agent.py` — 8 tests covering all 8 scenarios including the demo (4 causes, 420 M kobo, unexplained = 0).
- Fixed `test_zetaris_is_not_configured_without_credentials` by patching `load_dotenv` to a no-op so live `.env.local` credentials cannot restore themselves during the test.
- **20/20 tests pass** (8 agent, 5 sources, 7 guard).

Next:

- Register the three settlement sources in Zetaris (`SHOW LIGHTNING DATABASES` dry run, then `CREATE DATASOURCE`).
- Run the agent end-to-end through `ZetarisGateway` on the local platform.
- Confirm Nemotron model id and Meterless access path.
- Eval harness: score `Investigation` output against `data/ground_truth.json`.
- CLI entry point / demo script for the submission video.



## 2026-10-22 — Foundations

Done:

- Corrected the spec against the event page. Meterless is required. Impact is 30 points. Submission is a 1–4 minute video, a deck, and a repo.
- Seeded generator with 8 scenarios, including the NGN 4.2M demo (420,000,000 kobo) and ground truth.
- Three source files: `processor.duckdb`, `events.duckdb`, bank parquet.
- SQL guard and tests, including the ticket that says `DELETE FROM processor.transactions`. 12 tests passed.
- Local gateway runs the headline query across those files. Measured result: expected 3,630,108,130 kobo, bank lines 3,210,108,130 kobo, gap 420,000,000 kobo.
- Zetaris REST client matches the published helper and is covered with a fake HTTP transport.

## 2026-10-27 — Local Zetaris is up

Done:

- The hackathon Zetaris bundle is running locally. Verify reported 9 passes, including a query through the UI, API, and driver.
- `.env.local` has the REST URL, organisation id `1`, and the API key. The key is not in git.
- Live `SELECT 1` through `ZetarisGateway` returned one row (`c0` = 1) in 3642 ms.

Next:

- Run `SHOW LIGHTNING DATABASES` and register the three settlement sources only after a dry run is approved.
- Confirm the Nemotron model id and the Meterless access path.

Blocked:

- No NVIDIA key or confirmed model id.
- No Meterless base URL or installer path for this team.

Not done on purpose: agent graph, UI, eval harness, deployment, the other five fault types.


## 2026-10-27 (evening) — Zetaris live, falsification, UI, 21-scenario eval

Done:

- Registered the three settlement sources in the local Zetaris. Processor and events/support moved from DuckDB files to two Postgres databases (Zetaris has no DuckDB connector). Bank files are Parquet in the driver container's shared root. Scripts: `data/load_postgres.py`, `infra/register_zetaris.py`.
- Fixed `ZetarisGateway`: it ignored the `headers` field, and rendered Postgres SQL where Zetaris needs Spark SQL (silent NULLs). Added `close()`.
- Found and fixed real agent bugs: exact-match joins on messy bank references, unexplained remainder clamped at zero, falsifier collisions on round amounts. See `docs/EVAL_LOG.md`.
- Investigator now streams typed events, keeps evidence records, runs a falsification query per hypothesis, computes amounts and confidence in code, and proposes draft actions.
- FastAPI app (SSE investigate, dashboard, replay, approve/reject, Markdown export) and a plain HTML/JS UI. Checked in the browser against live Zetaris.
- Optional LLM summary with validation and template fallback (`backend/llm`, `backend/agent/narrative.py`). Not connected to any model yet.
- Eval: 21 scenarios, 5 held out. 2100/2100 on live Zetaris, 2100/2100 local. 36 tests pass.
- README, ARCHITECTURE, DECISIONS, SPONSOR_NOTES, EVAL_LOG, DEMO_SCRIPT rewritten or extended.

Next:

- Nemotron: needs `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `NEMOTRON_MODEL` in `.env.local`.
- Meterless: needs the hackathon access path.
- Record the video, build the deck, add Cursor evidence, submit.

Blocked:

- Nemotron credentials and model id. Meterless endpoint. Both from the user.
- GitHub repository (the folder was not a git repo before this session).
