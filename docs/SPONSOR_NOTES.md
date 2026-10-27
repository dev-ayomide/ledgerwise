# Sponsor notes

Checked 22 Oct 2026. If a fact is not in this file, it is not confirmed.

## Event rules

Source: https://hackathon.genai.works/event/open-agent-hackathon-2026

- Build window 22 Oct 2026 00:00 UTC through 27 Oct 2026 23:45 UTC. Registration closes 22 Oct 2026 23:59 UTC. Judging opens 27 Oct 00:00 UTC. Results 6 Nov 2026 16:00 UTC.
- One primary track. We are on Track 02, The Agent That Can Explain Why.
- Score: Impact 30, Technical 20, Innovation 15, Demo 15, Product and UX 10, Sponsor tech 10. Ties break on Impact, then earlier submission time. At least three judges.
- Track 02 cash: $1,600 / $1,200 / $900. Best use of NVIDIA Nemotron: DGX Spark Founder's Edition, listed at $4,699. The page does not say these stack.
- Rule 5: every submission must integrate Zetaris and Meterless, and teams must use Cursor for development. Integrate NVIDIA where it contributes.
- Submit a 1–4 minute video, a slide deck, a GitHub repo with README, and a written explanation of Zetaris, Meterless, Cursor, and NVIDIA.
- Pre-existing product code must be declared. This repo is written fresh.
- Judges include Michael Hay, CTO of Zetaris, and Michael Armentano, SpaceXAI.

## Zetaris

Sources:

- https://zetaris.github.io/getting-started/docs/connections/README.html
- https://github.com/zetaris/getting-started/blob/HEAD/scripts/zetaris_sql.py
- https://github.com/zetaris/getting-started/blob/HEAD/scripts/query_zetaris.py
- https://www.zetaris.com/zetaris-meta-data-lakehouse
- https://kbase.zetaris.com/knowledge/controlling-row-level-access

Confirmed:

- Two HTTP routes. Direct REST base ends in `/api/v1.0` (`ZETARIS_REST_URL`). UI proxy is the web origin (`ZETARIS_BASE_URL`) and is a different address.
- Direct query call used by their helper: `POST /sql-editor/sqls/run` with JSON `queryId` (UUID), `sql`, `source` = `SqlEditor`, `limit`. Headers: `Authorization: Bearer <API key>`, `X-Org-ID` (numeric organisation id), `X-Request-ID` (UUID).
- The helper reads the response field `data` as rows. It does not document column names. Our gateway uses a column field only when the payload actually has `columns`, `columnNames`, or `fields`. Otherwise columns are positional.
- Their docs say REST returns values as strings, and decimals may use exponent format. We turn plain integer strings into ints. We do not parse exponents with float.
- API keys are created in the UI under Management → API Tokens, shown once. Organisation ID is the numeric ID under Management → Organisation, not the name.
- UI-proxy helper, which we do not call yet: `POST /api/proxy/sql-editor/sqls/run-query` with `sql`, `limit`, and optional `engineId`.
- JDBC URL shape: `jdbc:zetaris:lightning@host:10000`. Driver class: `com.zetaris.lightning.jdbc.LightningDriver`. Needs their JAR. We do not guess the JAR path.
- `SELECT 1` and `SHOW LIGHTNING DATABASES` are the documented access checks. File and REST sources show up under `SHOW LIGHTNING DATABASES`. `CREATE DATASOURCE` sources show up under `SHOW DATASOURCES`.
- Send one statement per call. Do not create objects without an explicit go-ahead.
- Zetaris describes zero data movement: the query is pushed to the source and the result comes back. Column policies include Grant, Masked, Encrypted, Deny, and Hide. Masking applies to string columns. Not yet exercised on our data.
- Live local platform, 27 Oct 2026. The hackathon bundle is running on this Mac. Direct REST is `http://127.0.0.1:8888/api/v1.0`. Organisation id is `1` (name `zetaris`). `SELECT 1` through `ZetarisGateway` returned one row, column `c0` = 1, in 3642 ms. The UI, API, driver, and Postgres were healthy before that call. JDBC was not used.
- Zetaris also documents an MCP ("super MCP") and AgentFlow. Not used. Our agent will call the REST gateway. Revisit only if the trial makes MCP the practical path.

Confirmed by running it, 27 Oct 2026, local platform:

- Responses carry `headers` (column names), `data` (rows as strings), `total`, `timeUsed`. Our gateway had ignored `headers`; fixed.
- `SHOW DATASOURCES` and `SHOW LIGHTNING DATABASES` are read-only and worked. The platform ships NY_TAXI and TPCDS_DB.
- `CREATE DATASOURCE <name> DESCRIBE BY "<text>" OPTIONS (jdbcdriver, jdbcurl, username, password, fetchsize)` works for Postgres. The description allows only letters, digits, `_ . - ,`. The container reaches the Mac's Postgres at `host.docker.internal:5432`.
- Registering a datasource stores the connection only. `REGISTER DATASOURCE TABLES FROM <name>` (or `REGISTER DATASOURCE TABLE "<t>" FROM <name>`) makes tables queryable as `<name>.<table>`.
- Files: `CREATE LIGHTNING DATABASE bank DESCRIBE BY "..."` then `CREATE LIGHTNING FILESTORE TABLE <t> FROM bank FORMAT PARQUET OPTIONS (PATH "<path>", inferSchema "true")`. A local path works only under `/home/zetaris/customer-data/shared/` inside the driver container.
- Lightning SQL is Spark SQL. Postgres-rendered SQL (`REGEXP_REPLACE(..., 'g')`, `DOUBLE PRECISION`) fails or returns NULL.
- A single statement joined four sources (processor, events, support, bank Parquet) and returned the NGN 4,200,000 gap in about 0.7 to 2.3 s.
- No DuckDB connector is documented, so processor and events moved to Postgres. See DECISIONS.md.
- Column masking: not used. `settlement_account_ref` is masked in the loader (`data/load_postgres.py`) instead.

Not confirmed:

- The API key value. It lives only in `.env.local`.
- Zetaris governance and masking policies on our data.

## NVIDIA Nemotron

Confirmed by running it, 27 Oct 2026:

- Endpoint `https://integrate.api.nvidia.com/v1` (OpenAI-compatible). Key from build.nvidia.com settings, prefix `nvapi-`. `GET /models` lists 85 models.
- Callable with our key: `nvidia/nemotron-3-ultra-550b-a55b` (about 2 s), `nvidia/nemotron-3.5-bolt-e4b`, `nvidia/nemotron-3.5-lightning-30b-a3b` (returned empty content). 404 "Function not found for account": `nvidia/nemotron-3-super-120b-a12b`, `nvidia/nemotron-nano-3-30b-a3b`, `nvidia/llama-3.1-nemotron-{ultra-253b-v1,70b-instruct,51b-instruct}`, `nvidia/nemotron-4-340b-instruct`. 503 resource exhausted: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`.
- Chosen: `nvidia/nemotron-3-ultra-550b-a55b`. Default thinking leaks reasoning into `content` and hits the token limit. `chat_template_kwargs: {"enable_thinking": false}` in the request body fixes it (found by testing, not from documentation).

## Meterless

Sources: https://meterless.ai/ , /how-it-works.html , /engines.html , /relay.html , https://github.com/Meterless/Meterless

Confirmed from the public pages:

- Nightshift for Mac M1 and later is a free download. It exposes an OpenAI-compatible base URL, default `http://127.0.0.1:8088/v1`. The bearer token is in `<stateDir>/proxy-token`; the placeholder `rt-local` is rejected. Send `meterless-app: <id>` on every request and `meterless-scope: user` on chat. Model ids are routing modes (`meterless/auto|fast|deep|cheap|local|fusion`) plus `webllm/*` entries.
- Relay is a free Windows 10/11 app (github.com/meterless/relay). Not usable on this Mac. The public page does not explain how verified runs are saved as skills.
- No hackathon credit or access instructions were found on the Meterless pages or the hackathon page.

Confirmed by running it, 27 Oct 2026:

- `GET /v1/models` returns 14 ids and works with our token.
- `GET /health` (no `/v1`) returns provider status. Ours said: no provider key stored, no device model cached, "add one under Setup > Providers".
- With no lane, `meterless/local` returns 502 `privacy_floor_blocks_all_routes`, and other modes hang until the client times out. We check `/health` first so the app reports "unavailable" instantly instead of stalling.
- Not yet confirmed: a successful chat completion through Nightshift.

## Cursor

Development of this repo is happening in Cursor. `docs/BUILT_WITH_CURSOR.md` is the write-up the submission asks for. Screenshots are still missing.

## SpaceXAI

Zetaris's 6 Oct 2026 announcement describes the hackathon as pairing their data harness with SpaceXAI's Grok Build coding harness. The event rules name Cursor as the required development tool. We are building in Cursor. No second coding product is added unless the event workspace names one.
