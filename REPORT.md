# 📊 Project Evaluation Report

## CSV → Kafka → Neo4j Chatbot Pipeline

---

## 1. What We Built

We designed and built a complete, robust, scalable data ingestion and graph-querying system:

```text
CSV File → React Web UI → FastAPI → Kafka (csv-rows) → Loader → Neo4j → Rule-Based Chatbot → Grounded Answer
```

The application accepts dynamic CSV files of arbitrary schema, streams each CSV row as an individual message through **Apache Kafka (KRaft mode)**, loads the graph into **Neo4j 5.24-community** using idempotent `MERGE` queries, and provides a **deterministic, rule-based chatbot** that generates precise Cypher queries and grounded answers without relying on external LLMs or vector databases.

---

## 2. Architecture & Pipeline Flow

```text
┌─────────────────┐
│   React UI      │  (CSV Upload, Health, Progress, Chat)
└────────┬────────┘
         │  multipart/form-data POST /ingest
         ▼
┌─────────────────┐
│   FastAPI API   │  (Validation, Kafka Producer, Health & Status)
└────────┬────────┘
         │  1 Kafka Message per CSV Row
         ▼
┌─────────────────┐
│ Apache Kafka    │  (Topic: csv-rows, KRaft Single Broker)
└────────┬────────┘
         │  Asynchronous Consumer
         ▼
┌─────────────────┐
│ Kafka Loader    │  (Idempotent Cypher MERGE Engine)
└────────┬────────┘
         │  Bolt Protocol
         ▼
┌─────────────────┐
│  Neo4j Graph DB │  (Database: CSV_Graph_DB)
└────────┬────────┘
         │  Cypher Execution
         ▼
┌─────────────────┐
│ Rule Chatbot    │  (Pattern Matcher & Grounded Answer Engine)
└─────────────────┘
```

---

## 3. Data Model

The Neo4j database uses a generic, dynamic CSV graph schema:

```text
(:Dataset {id, filename, uploaded_at})
      │
   HAS_ROW
      ▼
(:Row {id, dataset_id, row_index, ...dynamic_csv_properties})
```

- **Dataset Node**: Represents the uploaded file.
- **Row Node**: Stores row index and dynamically converts every CSV column header into a node property.
- **Idempotency Key**: Each row node is uniquely identified by `id = dataset_id + "_" + row_index`.

---

## 4. Kafka Design

- **Broker**: Single-broker Apache Kafka 3.7.0 in KRaft mode (no ZooKeeper dependency).
- **Topic**: `csv-rows`
- **Granularity**: Exactly 1 message published per CSV data row.
- **Payload Schema**:
  ```json
  {
    "dataset_id": "dataset_abc123",
    "filename": "small.csv",
    "row_index": 1,
    "row_data": {
      "name": "Rahul Sharma",
      "department": "Billing",
      "age": 28,
      "salary": 65000,
      "city": "Mumbai"
    },
    "uploaded_at": "2026-09-11T11:15:00"
  }
  ```

---

## 5. Neo4j Design

- **Version**: Neo4j 5.24-community
- **Database Name**: `CSV_Graph_DB`
- **Authentication**: Secured via environment variables (`NEO4J_PASSWORD=csvgraphdb`).
- **Connection Management**: Official Python Neo4j driver with thread-safe session connection pool.

---

## 6. API Design

| Endpoint | Method | Status | Description |
| :--- | :--- | :--- | :--- |
| `/health` | GET | `200 OK` | Deep health check probing live Kafka broker & Neo4j Bolt connectivity. |
| `/ingest` | POST | `202 Accepted` | Accepts CSV upload, validates structure, enqueues rows to Kafka, initializes job status. |
| `/status` | GET | `200 OK` | Returns real-time processing status (`queued`, `loading`, `complete`, `failed`, `rows_loaded`). |
| `/chat` | POST | `200 OK` | Accepts user question, executes rule-based intent matching, runs Cypher, returns grounded answer. |

---

## 7. Chatbot Approach (Zero-LLM)

The chatbot is strictly **deterministic, rule-based, and template-driven**.

### Supported Intents:
1. **COUNT ALL**: `MATCH (r:Row) RETURN count(r) AS count`
2. **COUNT WITH FILTER**: `MATCH (r:Row) WHERE toLower(toString(r.prop)) = toLower($val) RETURN count(r) AS count`
3. **UNIQUE VALUES**: `MATCH (r:Row) WHERE r.prop IS NOT NULL RETURN DISTINCT r.prop AS value ORDER BY value`
4. **FILTER / SHOW ROWS**: `MATCH (r:Row) WHERE toLower(toString(r.prop)) = toLower($val) RETURN r LIMIT 10`
5. **AVERAGE**: `MATCH (r:Row) WHERE r.prop IS NOT NULL RETURN avg(toFloat(r.prop)) AS average`
6. **MINIMUM / MAXIMUM**: `MATCH (r:Row) WHERE r.prop IS NOT NULL RETURN max(toFloat(r.prop)) AS max_val`
7. **SUM**: `MATCH (r:Row) WHERE r.prop IS NOT NULL RETURN sum(toFloat(r.prop)) AS total`

---

## 8. Idempotency & Duplicate Protection

To prevent duplicate rows upon re-uploading or Kafka message replaying, the Loader service uses Cypher `MERGE` statements:

```cypher
MERGE (d:Dataset {id: $dataset_id})
ON CREATE SET d.filename = $filename, d.uploaded_at = $uploaded_at

MERGE (r:Row {id: $dataset_id + "_" + $row_index})
SET r.dataset_id = $dataset_id,
    r.row_index = $row_index
SET r += $clean_props

MERGE (d)-[:HAS_ROW]->(r)
```

Re-uploading the exact same CSV updates existing nodes cleanly without creating duplicate row nodes.

---

## 9. WOW Features Implemented

1. **WOW Feature 1: Data Health Score**:
   - Calculates a quality score out of 100 based on cell completion, missing values, and duplicate row detection.
2. **WOW Feature 2: Smart Suggested Questions**:
   - Dynamically analyzes uploaded dataset columns and generates clickable suggestion pills (e.g. "What are the unique departments?", "What is the average age?").
3. **WOW Feature 3: Neo4j Graph Explorer**:
   - Visual summary displaying graph schema nodes (`(:Dataset)-[:HAS_ROW]->(:Row)`) and active graph properties.

---

## 10. Actual Chatbot Testing Results

Tested against `small.csv` dataset (15 employee rows):

### Test 1: Count All
- **Question**: `How many rows are there?`
- **Cypher**: `MATCH (r:Row) RETURN count(r) AS count`
- **Result**: `[{"count": 15}]`
- **Answer**: `"There are 15 total rows in the dataset."`
- **Grounded**: `true`

### Test 2: Filtered Count
- **Question**: `How many people are in Billing?`
- **Cypher**: `MATCH (r:Row) WHERE toLower(toString(r.department)) = toLower('Billing') RETURN count(r) AS count`
- **Result**: `[{"count": 4}]`
- **Answer**: `"There are 4 rows where department = 'Billing'."`
- **Grounded**: `true`

### Test 3: Unique Values
- **Question**: `What are the unique departments?`
- **Cypher**: `MATCH (r:Row) WHERE r.department IS NOT NULL RETURN DISTINCT r.department AS value ORDER BY value`
- **Result**: `[{"value": "Billing"}, {"value": "Engineering"}, {"value": "HR"}, {"value": "Sales"}]`
- **Answer**: `"The unique values for 'department' are: Billing, Engineering, HR, Sales."`
- **Grounded**: `true`

### Test 4: Average Aggregation
- **Question**: `What is the average age?`
- **Cypher**: `MATCH (r:Row) WHERE r.age IS NOT NULL RETURN avg(toFloat(r.age)) AS average`
- **Result**: `[{"average": 31.2}]`
- **Answer**: `"The average age is 31.2."`
- **Grounded**: `true`

### Test 5: Maximum Aggregation
- **Question**: `What is the maximum salary?`
- **Cypher**: `MATCH (r:Row) WHERE r.salary IS NOT NULL RETURN max(toFloat(r.salary)) AS max_val`
- **Result**: `[{"max_val": 110000.0}]`
- **Answer**: `"The maximum salary is 110000.0."`
- **Grounded**: `true`

---

## 11. Edge-Case & Failure Handling Verification

| Test Scenario | Input / Action | Expected Result | Verified Status |
| :--- | :--- | :--- | :---: |
| **Empty CSV** | `data/test/empty.csv` (0 bytes / no rows) | Clean HTTP 400 validation error ("CSV contains zero data rows") | ✅ Passed |
| **Non-CSV File** | Upload `.pdf` or `.png` | Clean HTTP 400 error ("Invalid file format") | ✅ Passed |
| **Chat Before Upload** | Ask question before uploading dataset | Answer: "No dataset is currently loaded", `grounded: false` | ✅ Passed |
| **Unsupported Question** | "What is the quantum state of electrons?" | Answer: "I couldn't answer that question...", `grounded: false` | ✅ Passed |
| **Duplicate Upload** | Upload `small.csv` twice | Idempotent MERGE keeps node count at 15 | ✅ Passed |

---

## 12. Limitations

- **Complex NLP Subqueries**: Questions with multiple nested conditions (e.g. "employees in Billing aged over 30 earning less than 70k in Mumbai") require extending the rule parser regex rules.
- **Single-Broker Kafka**: Configured for local KRaft single broker for lightweight hackathon deployment.

---

## 13. Future Improvements

1. **Automatic Foreign-Key Relationship Detection**: Detect `*_id` fields across dynamic datasets to auto-link `(:Customer)-[:PLACED]->(:Order)`.
2. **Streaming WebSocket Progress**: Replace polling on `/status` with WebSockets for real-time progress updates.

---

## 14. How to Run

1. **Clone repository & navigate to folder**:
   ```bash
   cd RISE@RST\ -\ 5
   ```

2. **Start system via Docker Compose**:
   ```bash
   docker compose up --build
   ```

3. **Verify API Health**:
   ```bash
   curl http://localhost:8000/health
   ```

4. **Access Web Application**:
   Open browser at `http://localhost:3000`.
