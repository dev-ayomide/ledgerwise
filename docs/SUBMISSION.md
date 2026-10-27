# Submission write-up: Ledgerwise (Track 02, The Agent That Can Explain Why)

Repo: https://github.com/dev-ayomide/ledgerwise

## The problem and the user

A finance operations analyst at a payments company sees that yesterday's settlement is NGN 4.2M short. The processor database, the ledger, the bank settlement file and support tickets each say something different. Finding out why takes hours, and the answer is usually a pile of spreadsheets.

Ledgerwise investigates the gap, explains it with row-level evidence, challenges its own conclusions, and proposes fixes that a person approves. It never writes to any system.

## What it does

The user asks a question. The agent plans checks, runs one federated SQL query per check, proposes causes, tries to disprove each cause with a second query, computes amounts in code, and returns a report. Every claim links to the exact query and rows. Proposed actions are drafts. Nothing is executed.

Demo case: 21 October 2026, short by NGN 4,200,000. Four causes found, unexplained remainder NGN 0: a missing bank line (1.8M), a cutoff/timezone shift (1.5M), a retried webhook that created a duplicate credit (0.7M), a fee rate mismatch (0.2M).

## How Zetaris was used

All data access goes through Zetaris Lightning SQL on the local hackathon platform. The processor and the events/support data are two Postgres databases registered with `CREATE DATASOURCE`; the bank settlement files are Parquet registered with `CREATE LIGHTNING FILESTORE TABLE`. The first query of every investigation is one statement that joins all four logical sources (processor, events, support, bank files). Each investigation runs 3 to 9 queries, all through Zetaris. We found that Zetaris has no DuckDB connector (so the sources moved to Postgres), that it needs Spark SQL (a Postgres-rendered query silently returned NULLs), and that local files must sit under the driver container's shared root. These are in `docs/SPONSOR_NOTES.md`. Not used: Zetaris masking policies (accounts are masked in the loader), MCP, AgentFlow.

## How NVIDIA Nemotron was used

`nvidia/nemotron-3-ultra-550b-a55b` through NVIDIA's OpenAI-compatible endpoint writes the plain-language summary of each investigation from the structured report. A validator rejects the output if it cites an evidence id that does not exist or contains a number that is not in the facts, and a template is used instead. Nemotron does not choose queries or compute amounts. Its call latency and token counts are shown in the report. Notes: several listed Nemotron ids return 404 for our key, and Nemotron 3 needs thinking switched off (`chat_template_kwargs.enable_thinking=false`) or its reasoning fills the reply.

## How Meterless was used

Meterless Nightshift runs locally and exposes an OpenAI-compatible endpoint. After Nemotron writes the summary and the code-level checks pass, `meterless/fast` is asked to check every sentence against the facts and answer PASS or FAIL; FAIL falls back to the template. Nightshift routed the check to an NVIDIA Nemotron model and returned a compute receipt, whose id the report shows. This is a second, independent check, not a replacement for code validation. We did not use Relay (Windows only), and our replay feature is our own stored event stream, not Meterless.

## How Cursor was used

Cursor's agent worked on the project from 22 Oct 2026: reading the rules, the seeded data generator, the SQL guard, the first Zetaris client, and standing up the local Zetaris platform. Screenshots are in `docs/cursor/`, with the rest of the account in `docs/BUILT_WITH_CURSOR.md`. The 27 Oct work (falsification, streaming agent, app and UI, eval, Nemotron and Meterless integration, video and deck) was done in a separate Claude Code session, and we say so rather than credit it to Cursor.

## What is distinctive

- Falsification: every cause is challenged with a second query built to disprove it, and causes that fail are dropped and listed.
- Math in code: amounts, remainder and confidence are computed in Python from query results. Confidence comes from checkable signals, not model self-report.
- Honest uncertainty: scenarios with an unattributable short payment are reported as unexplained instead of inventing a cause.
- Safety: SQL guard (one SELECT, allowlisted tables, LIMIT cap), ticket text never enters a query or prompt, human approval for every action.
- Measured: 21 scenarios, 5 held out, 2100/2100 on live Zetaris. The first run on the 13 new scenarios scored 1995/2100 before a falsifier bug was fixed; the failure is logged.

## Limits (stated plainly)

- The investigation logic is deterministic rules plus falsification queries. A perfect score on synthetic scenarios from the same author shows the rules match the injected faults, not that they generalise.
- Six cause types are covered. Reversal without a ledger entry, rounding differences, duplicate bank lines, missing-webhook tickets and chargebacks are not.
- No public deployment: Zetaris runs locally, so the demo is a local run and the recorded video.

## What comes next

More fault types, a held-out set built by someone else, real masking policies in Zetaris, an LLM planner that proposes new checks within the same guard, and a pilot with an African payments operator.
