# Data In, Answers Out
## CSV &rarr; Kafka &rarr; Neo4j &rarr; Chatbot Pipeline — Full Project Report

---

## 1. What this project is

A complete, working data pipeline that takes an arbitrary CSV file uploaded through a web UI, streams every row through Apache Kafka, loads it into a Neo4j graph database, and answers natural-language questions about that data through a **deterministic, rule-based chatbot** — with **no LLM required at runtime**. An optional, tightly-scoped hybrid LLM step can assist with question *understanding* only, never with generating the final answer.

Every answer the chatbot gives is either backed by a real Cypher query against Neo4j (`grounded: true`) or is an honest refusal (`grounded: false`) — the system never invents data that isn't in the uploaded file.

---

## 2. High-level architecture

```mermaid
flowchart LR
    U["User\n(Browser)"] -->|"1. Upload CSV"| UI["UI\n(HTML/CSS/JS, nginx)"]
    UI -->|"2. POST /ingest"| API["API\n(FastAPI)"]
    API -->|"3. Publish 1 message per row"| KAFKA[("Kafka\ntopic: csv-rows\n(KRaft mode)")]
    KAFKA -->|"4. Consume messages"| LOADER["Loader\n(Kafka consumer)"]
    LOADER -->|"5. MERGE Dataset + Row nodes"| NEO4J[("Neo4j 5.x\nCSV_Graph_DB")]
    UI -->|"GET /status, /health"| API
    API -->|"read-only queries"| NEO4J
    U -->|"6. Ask a question"| UI
    UI -->|"7. POST /chat"| API
    API -->|"8. Rule-based intent match\n(+ optional LLM fallback\nfor classification only)"| CHATBOT["Chatbot logic"]
    CHATBOT -->|"9. Run fixed Cypher template"| NEO4J
    NEO4J -->|"10. Real result"| CHATBOT
    CHATBOT -->|"11. Grounded answer"| UI
```

**Why Kafka sits in the middle:** the API never writes row data to Neo4j directly. It publishes each row as a Kafka message and returns immediately; the Loader is a separate process that consumes those messages and writes to Neo4j at its own pace. This means a slow or temporarily unavailable Neo4j never blocks a CSV upload, and the ingestion pipeline can be scaled or restarted independently of the API.

---

## 3. Detailed request flow: uploading a CSV

```mermaid
sequenceDiagram
    participant B as Browser (UI)
    participant A as API (FastAPI)
    participant K as Kafka (csv-rows)
    participant L as Loader
    participant N as Neo4j

    B->>A: POST /ingest (multipart CSV file)
    A->>A: Validate: extension, non-empty,\nheader-only check
    alt validation fails
        A-->>B: 400 + human-readable error
    else validation passes
        A->>A: Parse rows, normalize column names
        A->>A: dataset_id = sha256(filename + bytes)[:16]
        A->>N: Create/merge Dataset node (metadata only)
        loop for every row
            A->>K: publish {dataset_id, row_index, row, columns, ...}
        end
        A-->>B: 202 Accepted {job_id, rows_received, status: queued}
    end

    loop continuously
        K->>L: deliver next message
        L->>N: MERGE (Dataset)-[:HAS_ROW]->(Row {row_key})
        L->>K: commit offset
    end

    loop every 1.5s
        B->>A: GET /status?job_id=...
        A->>N: live COUNT of Row/FailedRow nodes
        N-->>A: rows_loaded, rows_failed
        A-->>B: {status, rows_total, rows_loaded, rows_failed}
    end
```

### Key design decisions in this flow

| Decision | Why |
|---|---|
| `dataset_id = sha256(filename + file bytes)` | Re-uploading the *exact same* file always maps to the same `dataset_id`, so the Loader's `MERGE` is a true no-op the second time — this is what makes duplicate uploads idempotent. |
| Row key = `f"{dataset_id}_{row_index}"`, and `MERGE` (never `CREATE`) is used for every Row/Dataset/FailedRow write | Guarantees no duplicate nodes even if Kafka redelivers a message (crash/restart) or the same file is uploaded twice. |
| `/status` counts are **live Cypher queries** (`MATCH (d)-[:HAS_ROW]->(r) RETURN count(r)`), never an incrementing counter | A counter could double-count on message replay; a live count of real graph nodes cannot lie, and self-heals after any restart. |
| Failed rows are written as `(:FailedRow)` nodes instead of being silently dropped | `rows_failed` in `/status` is a real, queryable number — not a guess. |
| API never writes row/column data to Neo4j itself, only the Loader does | Satisfies the requirement that uploaded CSV *data* reaches Neo4j only through Kafka. The API is only allowed to write a `Dataset` metadata node so `/status` has something to report before the Loader starts. |

---

## 4. The Neo4j graph model

```mermaid
graph TD
    D["(:Dataset)\nid, filename, uploaded_at,\ntotal_rows, columns, status"] -->|HAS_ROW| R1["(:Row)\nrow_key, row_index,\n...CSV columns as properties"]
    D -->|HAS_ROW| R2["(:Row)"]
    D -->|HAS_ROW| R3["(:Row)"]
    F["(:FailedRow)\nrow_key, dataset_id,\nrow_index, error, raw"]
```

The model is intentionally generic (`Dataset` &rarr; `Row`) rather than a fixed schema, because the CSV structure is unknown ahead of time — any CSV with any columns can be uploaded, and every column becomes a property on the `Row` node.

---

## 5. The chatbot: question &rarr; Cypher &rarr; answer

```mermaid
flowchart TD
    Q["User question"] --> T["Tokenize + lowercase"]
    T --> R1{"Matches a\nrule-based pattern?\n(count / filter / list /\naggregate / min-max /\ndescribe / columns)"}
    R1 -->|"yes"| C1["Build the matching\nfixed Cypher template"]
    R1 -->|"no"| L{"ANTHROPIC_API_KEY set?"}
    L -->|"no"| REFUSE["'I don't have enough\ninformation...' grounded=false"]
    L -->|"yes"| LLM["LLM classifies question into\none of the SAME fixed intents\n(never writes Cypher,\nnever answers directly)"]
    LLM --> V{"Column/value it chose\nactually exist in this\ndataset's real schema?"}
    V -->|"no"| REFUSE
    V -->|"yes"| C1
    C1 --> EXEC["Run parameterized Cypher\nagainst Neo4j"]
    EXEC --> RES{"Real result\nfound?"}
    RES -->|"no"| REFUSE
    RES -->|"yes"| ANSWER["Build answer text FROM\nthe query result only\ngrounded=true"]
```

**The critical guarantee:** the LLM fallback (when enabled) is only ever allowed to pick *which* fixed Cypher template to run and *which* real column/value to plug into it — every choice it makes is re-validated against the dataset's actual schema before use. It never writes free-form Cypher and never generates the answer text; the answer is always built in code from the literal Neo4j query result. If the LLM (or the rule-based matcher) can't confidently map a question to a real template + real data, the honest refusal is returned instead of a guess.

### Supported question types (rule-based, no LLM needed)

| Intent | Example question | Cypher shape |
|---|---|---|
| Count all rows | "How many rows are there?" | `MATCH (r:Row) RETURN count(r)` |
| Count filtered | "How many rows are in Billing?" | `MATCH (r:Row {group:'Billing'}) RETURN count(r)` |
| Show matching rows | "Show Billing records" | `... WHERE r.group='Billing' RETURN r LIMIT 10` |
| List unique values | "What groups are available?" | `RETURN DISTINCT r.group` |
| Aggregation | "What is the average age?" | `RETURN avg(toFloat(r.age))` |
| Min / max | "What is the maximum age?" | `RETURN max(toFloat(r.age))` |
| Schema | "How many columns are there?" | reads `Dataset.columns` |
| Describe | "Describe the dataset" | row count + column list |

---

## 6. Component breakdown

```mermaid
graph TB
    subgraph "ui/ (vanilla HTML/CSS/JS, served by nginx)"
        UI1["index.html — dashboard, upload,\ningestion status, graph explorer,\nchatbot, activity log, system info"]
        UI2["app.js — all real API calls,\nno hardcoded demo data"]
    end
    subgraph "api/ (FastAPI)"
        R1["routes/ingest.py — validate + parse CSV,\npublish to Kafka"]
        R2["routes/status.py — live progress from Neo4j"]
        R3["routes/health.py — real Kafka + Neo4j checks"]
        R4["routes/chat.py — question in, grounded answer out"]
        R5["routes/insights.py — Data Health Score,\nSuggested Questions, Graph sample"]
        S1["services/chatbot.py — rule-based\nquestion-to-Cypher matching"]
        S2["services/llm_intent.py — optional hybrid\nLLM classifier (off by default)"]
        S3["services/kafka_producer.py"]
        S4["services/neo4j_service.py"]
        S5["services/csv_utils.py — validation + parsing"]
    end
    subgraph "loader/ (Kafka consumer)"
        L1["consumer.py — poll Kafka,\ncommit offset per message"]
        L2["neo4j_loader.py — MERGE Dataset/Row,\nrecord FailedRow on error"]
    end
    subgraph infra ["Infrastructure (docker-compose.yml)"]
        KI["Kafka 3.7.0, KRaft, single broker"]
        NI["Neo4j 5.24 Community"]
    end
```

---

## 7. WOW features (beyond the core requirements)

1. **Data Health Score** (`GET /insights`) — a 0-100 score computed from real column completeness (% non-missing values per column) and load completeness (rows loaded vs. rows total). Never a fabricated number.
2. **Smart Suggested Questions** — generated dynamically from the dataset's *actual* columns, so the suggestions always work against whatever was uploaded.
3. **Graph Explorer** — a dependency-free, pure-SVG radial layout of the real `Dataset` and sampled `Row` nodes (`GET /graph`), with click-to-inspect real node properties. No third-party graph-visualization library was added, so it carries zero risk to the core pipeline's build.

---

## 8. Reliability & error handling

- **Startup readiness:** the API and Loader both retry connecting to Kafka and Neo4j on startup instead of assuming the container being "up" means the service is ready; `docker-compose.yml` also uses real health checks (`service_healthy`) so dependent containers wait properly.
- **Idempotent loading:** every write uses `MERGE` on a stable key (`dataset_id + row_index` for rows, content hash for `dataset_id` itself) — uploading the same file twice never creates duplicate nodes.
- **Input validation:** empty files, header-only files, and non-`.csv` files all return clean `400` responses with a specific message — never a raw `500`.
- **Global exception safety net:** any unanticipated server error still returns clean JSON instead of a bare crash page (added after a real-world CSV — one with a stray `\r` character inside a text field — triggered an uncaught `csv.Error`; the parser was hardened and this safety net was added on top).
- **Large files:** nginx's reverse proxy is configured for large request bodies and long timeouts (a 60,000-row / 7.5 MB CSV was verified to upload and fully load with zero failures).
- **Non-root containers, pinned image versions:** `apache/kafka:3.7.0`, `neo4j:5.24-community` — no `latest` tags anywhere; the `api`, `loader`, and `ui` containers all run as a dedicated non-root user.

---

## 9. Technology stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML / CSS / JavaScript (Tailwind via CDN), served by nginx |
| Backend API | Python 3.11, FastAPI |
| Message broker | Apache Kafka 3.7.0, KRaft mode, single broker |
| Database | Neo4j 5.24 Community Edition, official Python driver |
| Chatbot | Rule-based Cypher templates; optional hybrid LLM (Anthropic API) for question classification only |
| Containerization | Docker + Docker Compose |

---

## 10. What was actually verified (not just written)

- Clean `docker compose down -v && docker compose up --build` from a fully empty volume — all 5 containers reach healthy/running with zero manual steps.
- `GET /health` returns real `kafka_connected` / `neo4j_connected` booleans backed by an actual Kafka metadata fetch and a Neo4j `verify_connectivity()` call.
- A 15-row CSV traced end-to-end: `/ingest` &rarr; Kafka topic `csv-rows` &rarr; Loader logs &rarr; confirmed present via `cypher-shell` directly against `csv-graph-db`.
- The same 15-row CSV uploaded twice: Neo4j still contains exactly 15 `Row` nodes.
- A 60,000-row / 7.5 MB CSV uploaded through the real UI: all 60,000 rows loaded, 0 failures.
- Chat tested for count-all, count-filtered, average, max, distinct-values, schema, and describe intents, plus deliberately off-topic and nonsense questions — every response carries the correct `grounded` flag.
- Empty CSV, header-only CSV, and a non-`.csv` file all return clean `400`s, never a `500`.
- Full UI click-path exercised in a real browser: upload &rarr; live progress &rarr; dashboard KPIs/preview table populate from Neo4j &rarr; suggested-question chip clicked &rarr; grounded chat answer with real Cypher/result shown &rarr; Graph Explorer node click shows real row properties.

---

## 11. Known limitations

- The rule-based chatbot cannot understand unlimited natural-language phrasing by design; the optional LLM fallback widens coverage but is still restricted to the same fixed set of query templates and never fabricates an answer.
- `/chat` and `/status` operate on one dataset at a time (the most recently uploaded, or an explicit `job_id`) — there is no cross-dataset querying.
- A Loader restart can incur a short (up to ~30-45s) delay before Kafka reassigns its consumer group partitions; this affects latency only, never correctness, since `MERGE` makes any replay safe.

---

## 12. How to run it

```bash
git clone <this-repo>
cd <repo-folder>
cp .env.example .env   # fill in NEO4J_PASSWORD at minimum
docker compose up --build
```

Then open the UI (default `http://localhost:3001`) and:
1. Upload a `.csv` file.
2. Watch the live ingestion progress.
3. Ask a question about the data in the chat panel.
4. Explore the graph in the Graph Explorer tab.

See `REPORT.md` for the original design-decision log and `README.md` for the full project specification this implementation follows.
