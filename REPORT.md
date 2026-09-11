# REPORT — Data In, Answers Out

## What was built

A complete, verified, working implementation of the CSV → Kafka → Neo4j →
Chatbot pipeline described in `README.md`:

```
UI (React/Vite, served by nginx)
  → API (FastAPI)
    → Kafka (topic: csv-rows, KRaft single broker)
      → Loader (Kafka consumer)
        → Neo4j 5.24 Community
          → Rule-based chatbot (no LLM, template-to-Cypher)
```

All 5 services run under `docker compose up --build` with no manual steps,
using health checks and `service_healthy` dependencies so the API/Loader
never assume Kafka or Neo4j are ready just because the container started.

## Key design decisions (and deviations from the literal README text)

1. **Neo4j database name.** The README specifies `CSV_Graph_DB`. Neo4j
   database names must match `^[a-z][a-z0-9.-]*$` (lowercase, no
   underscores) — `CSV_Graph_DB` is rejected at startup ("contains illegal
   characters"). We use `csv-graph-db` instead (set via `NEO4J_DATABASE` in
   `.env`), which is the closest legal equivalent. This is a hard
   constraint of Neo4j 5.x Community, not a design choice.

2. **Row data reaches Neo4j only through Kafka.** The API never writes CSV
   row content to Neo4j. It only creates the `(:Dataset)` node
   (metadata: id/filename/total_rows/columns) synchronously so `/status`
   has something to report immediately after `/ingest` returns, before the
   Loader has consumed anything. All `(:Row)` nodes and their properties are
   written exclusively by the Loader, from Kafka messages.

3. **Deterministic dataset IDs for true idempotency.** `dataset_id` is
   `sha256(filename + file bytes)[:16]`, not a random UUID. This means
   uploading the exact same CSV twice reuses the same `dataset_id`, so the
   Loader's `MERGE (r:Row {row_key: dataset_id + "_" + row_index})` is a
   real no-op on the second upload — verified: after two uploads of the
   same 15-row file, Neo4j contains exactly 15 `Row` nodes, not 30.

4. **`/status` is computed live from graph state, never from a counter.**
   `rows_loaded` = `count((d)-[:HAS_ROW]->(r:Row))`, `rows_failed` =
   `count((:FailedRow {dataset_id}))`. Because these are live counts of
   real nodes (not an incrementing counter), replaying Kafka messages or
   restarting the Loader can never inflate progress — it's naturally
   idempotent, matching the "must not be hardcoded" requirement.

5. **Failed rows are stored, not silently dropped.** Any row that a Loader
   can't process is written to a `(:FailedRow)` node with its error and raw
   payload (also `MERGE`d on a stable key), so `/status.rows_failed` is
   real and inspectable.

6. **Chatbot column/value discovery is dynamic.** Since CSV columns are
   unknown ahead of time, the chatbot introspects the current dataset's
   column names (`Dataset.columns`, set at ingest) and, for filter-style
   questions, scans distinct values per column to match a token in the
   question. All Cypher is built from a small set of parameterized
   templates — never from raw string interpolation of user input into
   values (only column names, which come from the dataset's own header
   row, are interpolated into the query text; all *values* are bound
   parameters).

## WOW features implemented

- **Data Health Score** (`GET /insights?job_id=`) — a 0–100 score derived
  from real column completeness (% non-missing) and load completeness,
  computed from actual Neo4j data, not fabricated.
- **Smart Suggested Questions** — generated from the dataset's actual
  columns (e.g. "What is the average age?" only appears if a numeric-ish
  column exists), shown as clickable chips in the chat panel.
- **Graph Explorer** (`GET /graph?job_id=&limit=`) — a dependency-free,
  pure-SVG radial layout of the `Dataset` node and up to 40 sampled `Row`
  nodes, with click-to-inspect node properties. No graph-viz library was
  added, so it carries no risk to the core pipeline's bundle/build.

## Verification performed (not just written — actually run)

- `docker compose down -v` + `docker compose up --build` from a fully
  clean volume: all 5 containers reach a healthy/running state with zero
  manual steps.
- `GET /health` returns real `kafka_connected`/`neo4j_connected` booleans
  backed by an actual Kafka metadata fetch and a Neo4j `verify_connectivity()`
  call (not "containers are up").
- Uploaded a 15-row CSV: rows traced end-to-end through `/ingest` →
  Kafka topic `csv-rows` → Loader logs ("Loaded row N of dataset ...") →
  confirmed present via `cypher-shell` directly against `csv-graph-db`.
- Uploaded the same 15-row CSV twice: Neo4j still contains exactly 15
  `Row` nodes (idempotency/`MERGE` verified).
- Uploaded a 5,000-row CSV: `/status` showed live incrementing progress
  (`rows_loaded` climbing), reached `rows_loaded: 5000, status: complete`,
  confirmed with a direct `MATCH (r:Row) RETURN count(r)` = 5000.
- Chat tested for: count-all, count-filtered, average, max, distinct
  values, and an unsupported/nonsense question — every response includes
  `answer`, `cypher`, `result`, and a correct `grounded` flag; the
  unsupported question correctly returns
  `"I don't have enough information..."` with `grounded: false`.
- Chat before any upload returns `"No dataset has been uploaded yet..."`
  with `grounded: false`.
- Empty CSV, header-only CSV, and a non-`.csv` file (`.pdf`) all return
  clean `400` responses with the exact README-specified messages — no
  `500`s.
- Full UI click-path exercised in a real browser against the live stack:
  file selected → client-side preview rendered → Upload clicked → real
  progress bar animated to 100% → Data Health Score panel rendered (score
  100) → clicked a suggested-question chip → chat bubble appeared with the
  correct grounded answer and "✓ Grounded in Neo4j" → Graph Explorer
  rendered the Dataset node plus 5 Row nodes as SVG circles.
- Confirmed all custom containers (`api`, `loader`, `ui`) run as a
  non-root user (`id` inside each container), and no image in
  `docker-compose.yml`/Dockerfiles uses the `latest` tag.

## Known limitations

- The chatbot's value-matching is substring/token based; it will not
  understand highly unusual phrasings of a question, by design (see
  README "Current Limitations").
- `/status` and `/chat` operate on one dataset at a time
  (most-recently-uploaded, or an explicit `job_id`); there is no
  cross-dataset querying.
- Kafka consumer-group rebalancing after a Loader restart can add a short
  (up to ~30–45s) delay before consumption resumes, due to Kafka's default
  session timeout. This does not affect correctness (MERGE is idempotent
  and offsets are committed per-message), only latency after a restart.
