# Decisions

## 2026-10-22 — Track 02, and Meterless is in scope

The official rules require every submission to integrate Zetaris and Meterless, and to use Cursor for development. Meterless is not a leftover. Impact is 30 of 100, so the demo has to feel like a settlement break a person would forward, with the eval as the proof rather than the product.

## 2026-10-22 — Local DuckDB is the test double

`LocalDuckDBGateway` attaches three separate files (processor database, events database, bank parquet) and runs one SQL statement across them. That is how we test the guard and the gap math before a Zetaris account exists. The README and the gateway docstring say this is not the product. `ZetarisGateway` is the path the demo will use.

## 2026-10-22 — Zetaris client follows the published REST helper

Direct REST is `POST {ZETARIS_REST_URL}/sql-editor/sqls/run` with `queryId`, `sql`, `source: SqlEditor`, and `limit`, plus bearer auth, `X-Org-ID`, and `X-Request-ID`. That is what `RestChannel` does in the public [zetaris/getting-started](https://github.com/zetaris/getting-started) `scripts/zetaris_sql.py`. On 27 Oct 2026 that call succeeded against the local platform: `SELECT 1` returned `c0` = 1. JDBC stays unused. Source registration SQL is not guessed.

## 2026-10-22 — Eight scenarios on day 1, not twenty

The generator ships five fault types, the NGN 4.2M combination, one red herring, and one unexplained batch header. The other five fault types and the held-out set wait until the agent loop exists. Baseline rows have messy narrations and some inexact `matched_reference` values. Fault rows keep exact references so the kobo totals stay exact.

## 2026-10-22 — Query log is in memory for now

Every guarded query records SQL, tables, duration, and row count on the gateway. Postgres comes with the investigation store. No secrets go in the log.

## 2026-10-22 — No Meterless client until the access path is real

Public docs describe Nightshift as a local OpenAI-compatible base URL, and Relay as replayable verified runs. There is no confirmed hackathon endpoint in this repo. A homemade JSON file will not be described as Meterless.

## 2026-10-27 — Processor and events moved from DuckDB files to Postgres for Zetaris

Zetaris registers JDBC sources and Parquet/CSV files. Its docs name no DuckDB connector. The generator still writes DuckDB files (cheap, deterministic), and `data/load_postgres.py` copies them into two Postgres databases, `ledgerwise_processor` and `ledgerwise_events`, on the local Homebrew Postgres. The user approved this. Zetaris sees four logical sources: `processor` and `events` and `support` (JDBC; `support` and `events` point at the same database) and `bank` (Parquet). That is three physical systems: the processor Postgres database, the events Postgres database (which serves both `events` and `support`), and the Parquet files.

## 2026-10-27 — Zetaris gets Spark SQL, not Postgres SQL

Lightning SQL is Spark SQL. Rendering with sqlglot's postgres dialect produced `REGEXP_REPLACE(..., 'g')`, which Spark reads as a position argument and turns into NULL. Two queries returned zero rows with no error, so the agent looked fine and was wrong. `ZetarisGateway` now renders `spark`. `tests/test_zetaris_dialect.py` pins it. Percent arithmetic also moved to integers.

## 2026-10-27 — Bank files go in the driver container's shared root

`CREATE LIGHTNING FILESTORE TABLE` rejected `/home/zetaris/customer-data/<dir>` ("Invalid file path to access") and accepted `/home/zetaris/customer-data/shared/<dir>`, which matches `ZETARIS_LOCAL_FILE_SYSTEM_ROOT_PATH` in the platform compose file. `infra/register_zetaris.py` copies the files there with `docker cp`.

## 2026-10-27 — Plain HTML/JS frontend instead of Next.js

Five hours were left on submission day. A Next.js app adds a build, a deploy and type mirroring for no gain in what judges see. The UI is `frontend/` (static HTML, CSS, JS) served by FastAPI. `tests/test_events.py` checks that the UI handles every backend event type. No public deployment: Zetaris runs on this Mac, so a hosted copy could not reach the data. The submission demo is a local run plus the recorded video.

## 2026-10-27 — The reasoning is rules plus falsification; the LLM only narrates

Each cause has a detector query and a separate falsifier query. Amounts and confidence come from code. When NVIDIA credentials are set, the model writes the plain-language summary, and its output is rejected if it cites an unknown evidence id or contains a number not in the facts. Without credentials a template writes it, and the UI says which one. We do not call this model-driven investigation.

## 2026-10-27 — Falsifier counts orphan lines only

See `docs/EVAL_LOG.md`, run 1.

## 2026-10-27 — Datasets and held-out set

Scenarios grew from 8 to 21 (two-fault, three-fault, two more red herrings, two with an unattributable short payment). New scenarios are appended after the original eight so the first eight stay byte-identical. Cutoff scenarios use odd dates so the next day's bank lines do not leak into another scenario. Five scenarios are marked `held_out` and were not tuned against.

## 2026-10-27 — Nemotron writes the summary only; Meterless verifies it

Nemotron Ultra gets the report facts and writes the summary. Code-level validation (known evidence ids, numbers present in the facts) runs first and is the real gate. Meterless Nightshift is then asked, as an independent model, to check the summary and answer PASS or FAIL; FAIL falls back to the template. This uses Meterless's documented OpenAI-compatible endpoint. It is not Relay and not replayable skills. If Nightshift has no lane the report says "unavailable" and nothing else changes.
