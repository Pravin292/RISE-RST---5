# 🚀 Data In, Answers Out

## CSV → Kafka → Neo4j Chatbot Pipeline

A complete data ingestion and querying system that takes a **dynamic CSV file**, streams every row through **Apache Kafka**, loads the data into **Neo4j**, and provides a **rule-based natural-language chatbot** that answers questions using Cypher queries against the graph.

> **Important:** This project does **not use an LLM**.
> The chatbot uses deterministic question-pattern matching and Cypher query templates. All answers are generated from actual data stored in Neo4j.

---

# 📌 Table of Contents

1. [Problem Statement](#-problem-statement)
2. [Our Solution](#-our-solution)
3. [Complete System Flow](#-complete-system-flow)
4. [Architecture](#-architecture)
5. [Main Components](#-main-components)
6. [Technology Stack](#-technology-stack)
7. [Project Structure](#-project-structure)
8. [CSV Ingestion Flow](#-csv-ingestion-flow)
9. [Kafka Flow](#-kafka-flow)
10. [Neo4j Data Model](#-neo4j-data-model)
11. [Idempotent Loading](#-idempotent-loading)
12. [Chatbot](#-chatbot)
13. [API Endpoints](#-api-endpoints)
14. [UI Features](#-ui-features)
15. [Error Handling](#-error-handling)
16. [Docker Setup](#-docker-setup)
17. [Environment Variables](#-environment-variables)
18. [How to Run](#-how-to-run)
19. [Testing](#-testing)
20. [Demo Flow](#-demo-flow)
21. [Design Decisions](#-design-decisions)
22. [Limitations](#-limitations)
23. [Future Improvements](#-future-improvements)
24. [Team](#-team)

---

# 🎯 Problem Statement

Companies receive CSV and spreadsheet data from different systems such as CRM exports, partner systems, support tools, and other applications.

The traditional process is:

```text
CSV
 ↓
Manual Import
 ↓
Database
 ↓
Manual Query
 ↓
Answer
```

This project automates the complete process.

Our goal is to build:

```text
CSV
 ↓
UI
 ↓
API
 ↓
Kafka
 ↓
Loader
 ↓
Neo4j
 ↓
Chatbot
 ↓
Answer
```

The user should be able to upload a CSV they have never shown the system before and ask questions about the uploaded data without manually writing database queries.

The official challenge requires a complete working pipeline from CSV upload to grounded chatbot answers, with Docker-based deployment and no manual setup during execution.

---

# 💡 Our Solution

We built a five-part system:

```text
┌───────────────┐
│      UI       │
│ Upload + Chat │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│      API      │
│ FastAPI       │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│     Kafka     │
│   csv-rows    │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│    Loader     │
│ Kafka Consumer │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│     Neo4j     │
│ Graph Database│
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Rule-Based    │
│   Chatbot     │
└───────────────┘
```

The important design principle is:

> **Build the pipe before the logic.**

The ingestion pipeline is completed first, and the chatbot works on top of the actual Neo4j data. This follows the recommended strategy from the challenge handout.

---

# 🔄 Complete System Flow

## Step 1 — User uploads CSV

The user opens the web application and selects a CSV file.

Example:

```text
customers.csv
```

The UI sends the file to:

```http
POST /ingest
```

---

## Step 2 — API receives the CSV

The API accepts the multipart form-data file.

It does **not** directly write the CSV into Neo4j.

Instead, it processes the CSV row-by-row and publishes each row to Kafka.

```text
CSV
 ↓
API
 ↓
Kafka
```

The challenge specifically requires that uploaded CSV data reaches Neo4j **only through Kafka**, not directly from the upload handler.

---

# 📦 Step 3 — Kafka receives rows

Kafka contains the topic:

```text
csv-rows
```

Every CSV row becomes one Kafka message.

Example:

```text
CSV:

Name,Age,Group
Rahul,22,Billing
Priya,24,HR
Arun,25,Billing
```

Kafka receives:

```text
Message 1 → Rahul,22,Billing
Message 2 → Priya,24,HR
Message 3 → Arun,25,Billing
```

This decouples the upload process from the database loading process.

If Neo4j is temporarily unavailable, messages can remain in Kafka instead of causing the upload process to fail immediately.

---

# 🚚 Step 4 — Loader consumes Kafka

The Loader acts as a Kafka consumer.

It continuously reads messages from:

```text
csv-rows
```

For every message:

```text
Kafka message
      ↓
Loader
      ↓
Convert row
      ↓
Neo4j MERGE
```

The Loader does not directly modify the original CSV file.

---

# 🗄️ Step 5 — Neo4j stores the data

Neo4j is used as the graph database.

The database name is:

```text
CSV_Graph_DB
```

The initial graph model is intentionally generic because the CSV structure is dynamic.

```text
(:Dataset)
      |
   HAS_ROW
      |
    (:Row)
```

Example:

```text
(:Dataset {
    id: "dataset_001",
    filename: "customers.csv",
    uploaded_at: "..."
})
        |
     HAS_ROW
        |
        ▼
(:Row {
    row_index: 1,
    name: "Rahul",
    age: 22,
    group: "Billing"
})
```

The challenge recommends keeping the graph model simple as:

```text
(:Dataset {id, filename, uploaded_at})
        |
     HAS_ROW
        |
(:Row {row_index, col_1, col_2, ...})
```

and enriching it only if time permits.

---

# 🔐 Idempotent Loading

One of the most important requirements is **no duplicate rows**.

If the same CSV is uploaded twice:

```text
Upload 1 → 1000 rows
Upload 2 → same 1000 rows
```

The database must not contain:

```text
2000 rows ❌
```

It should contain the same logical dataset without duplicate row nodes.

The Loader therefore uses:

```cypher
MERGE
```

instead of:

```cypher
CREATE
```

A stable identifier is based on:

```text
dataset_id + row_index
```

Example:

```text
dataset_001_1
dataset_001_2
dataset_001_3
```

If the row already exists, `MERGE` prevents another node from being created.

The challenge explicitly states that every row must be written using `MERGE` with a stable key and that using `CREATE` can cause duplicates during replay or restart.

---

# 🤖 Chatbot

## No LLM

This project intentionally does not use an LLM.

Instead, the chatbot follows:

```text
User Question
      ↓
Question Parser
      ↓
Intent Detection
      ↓
Cypher Template
      ↓
Neo4j
      ↓
Actual Result
      ↓
Natural-Language Answer
```

The challenge explicitly allows a chatbot based on question-to-Cypher template matching.

---

# 🧠 Supported Chatbot Intents

The chatbot supports common data questions using predefined patterns.

## 1. Count all rows

Example:

```text
How many rows are there?
```

Cypher:

```cypher
MATCH (r:Row)
RETURN count(r)
```

---

## 2. Count rows matching a value

Example:

```text
How many rows are in Billing?
```

Possible Cypher:

```cypher
MATCH (r:Row)
WHERE r.group = 'Billing'
RETURN count(r)
```

---

## 3. Show matching rows

Example:

```text
Show Billing records
```

Cypher:

```cypher
MATCH (r:Row)
WHERE r.group = 'Billing'
RETURN r
LIMIT 10
```

---

## 4. List unique values

Example:

```text
What groups are available?
```

Cypher:

```cypher
MATCH (r:Row)
RETURN DISTINCT r.group
```

---

## 5. Aggregation

Example:

```text
What is the average age?
```

Cypher:

```cypher
MATCH (r:Row)
RETURN avg(toFloat(r.age))
```

---

## 6. Minimum / Maximum

Example:

```text
What is the maximum age?
```

Cypher:

```cypher
MATCH (r:Row)
RETURN max(toFloat(r.age))
```

---

# 🛡️ Grounded Answers

The chatbot must never invent information.

If Neo4j contains the required information:

```json
{
  "answer": "There are 128 Billing rows.",
  "cypher": "MATCH (r:Row {group: 'Billing'}) RETURN count(r)",
  "result": [
    {
      "count(r)": 128
    }
  ],
  "grounded": true
}
```

If the graph cannot answer the question:

```json
{
  "answer": "I don't have enough information in the uploaded data to answer this question.",
  "cypher": "...",
  "result": [],
  "grounded": false
}
```

We never generate a confident answer without supporting graph data.

This is one of the central requirements of the challenge.

---

# 🔌 API Endpoints

The backend exposes four main endpoints.

---

## `POST /ingest`

Uploads a CSV.

### Request

```http
POST /ingest
Content-Type: multipart/form-data
```

Field:

```text
file
```

### Example response

```json
{
  "job_id": "b3f1",
  "rows_received": 1000,
  "status": "queued"
}
```

The challenge specifies `202 Accepted` for this endpoint.

---

# `GET /status`

Returns real ingestion progress.

Example:

```http
GET /status?job_id=b3f1
```

Response:

```json
{
  "job_id": "b3f1",
  "status": "loading",
  "rows_total": 1000,
  "rows_loaded": 640,
  "rows_failed": 3
}
```

Possible states:

```text
queued
loading
complete
failed
```

The values must represent actual processing progress and must not be hardcoded.

---

# `GET /health`

Checks whether the required services are genuinely available.

Example:

```json
{
  "status": "ok",
  "kafka_connected": true,
  "neo4j_connected": true
}
```

The API must not report `ok` merely because Docker containers have started.

Kafka and Neo4j must actually be reachable.

---

# `POST /chat`

Accepts a natural-language question.

### Request

```json
{
  "question": "How many rows belong to the Billing group?"
}
```

### Response

```json
{
  "answer": "There are 128 rows where group = 'Billing'.",
  "cypher": "MATCH (r:Row {group: 'Billing'}) RETURN count(r)",
  "result": [
    {
      "count(r)": 128
    }
  ],
  "grounded": true
}
```

The API always exposes:

* Answer
* Cypher
* Raw result
* Grounded status

This makes the chatbot verifiable.

---

# 🖥️ UI Features

The frontend provides a simple interface for the complete workflow.

## CSV Upload

```text
[ Choose CSV ]
[ Upload ]
```

---

## CSV Preview

After selecting the file, the UI previews received rows.

Example:

```text
Name       Age       Group
--------------------------------
Rahul      22        Billing
Priya      24        HR
Arun       25        Billing
```

---

## Loading Progress

The UI displays ingestion progress:

```text
Loading...

████████████████░░░░ 80%

Total: 5000
Loaded: 4000
Failed: 3
```

---

## Chat Interface

Example:

```text
Ask a question about your data:

[ How many rows are in Billing? ]

                         [Ask]
```

---

## Query Transparency

Every chatbot answer can show:

```text
Answer:
There are 128 Billing rows.

Generated Cypher:
MATCH (r:Row {group: 'Billing'})
RETURN count(r)

Database Result:
128

✓ Grounded in Neo4j
```

This makes it clear that the answer came from the graph.

---

# 🧯 Error Handling

The system is designed to handle invalid input without crashing.

## Empty CSV

```text
Error:
The uploaded CSV contains no data.
```

---

## Header but zero rows

```text
Error:
The CSV contains headers but no data rows.
```

---

## Non-CSV file

```text
Error:
Please upload a valid CSV file.
```

---

## Chat before upload

```text
No dataset has been uploaded yet.
I cannot answer this question.
```

---

## Question with no supporting data

```text
I don't have enough information in the uploaded data to answer this question.
```

```json
{
  "grounded": false
}
```

The challenge specifically requires testing empty files, zero-row files, non-CSV files, unsupported questions, and questions asked before an upload.

---

# 🐳 Docker Architecture

Everything runs using one:

```text
docker-compose.yml
```

Main services:

```text
UI
API
Kafka
Loader
Neo4j
```

The target is:

```bash
docker compose up
```

and the entire system should start without manual service startup.

The official requirement is that `docker compose up` should bring up the UI, API, Kafka, Neo4j, and Loader without manual steps.

---

# 🏗️ Suggested Project Structure

```text
project-root/
│
├── docker-compose.yml
├── .env
├── .gitignore
├── README.md
├── REPORT.md
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── routes/
│   │   ├── ingest.py
│   │   ├── status.py
│   │   ├── health.py
│   │   └── chat.py
│   ├── services/
│   │   ├── kafka_producer.py
│   │   ├── neo4j_service.py
│   │   └── chatbot.py
│   └── models/
│
├── loader/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── consumer.py
│   └── neo4j_loader.py
│
├── ui/
│   ├── Dockerfile
│   ├── index.html
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   └── app.js
│   └── package.json
│
├── data/
│   └── test/
│       ├── small.csv
│       ├── large.csv
│       └── broken.csv
│
└── neo4j/
    └── init/
```

The exact internal folder structure can be changed as needed. The important requirement is that the externally visible behavior and API contracts remain correct.

---

# 🧰 Technology Stack

| Component        | Technology                   |
| ---------------- | ---------------------------- |
| Frontend         | React or HTML/CSS/JavaScript |
| Backend          | Python + FastAPI             |
| Message Broker   | Apache Kafka                 |
| Kafka Mode       | KRaft                        |
| Kafka Brokers    | Single broker                |
| Database         | Neo4j 5.x Community          |
| Database Driver  | Official Neo4j Python Driver |
| Containerization | Docker + Docker Compose      |
| Chatbot          | Rule-based Cypher templates  |

Recommended versions from the challenge:

```text
Python: 3.11
Kafka: apache/kafka:3.7.0
Neo4j: neo4j:5.24-community
```

The challenge recommends Python 3.11 or Node.js 18, Kafka in single-broker KRaft mode, Neo4j 5.x Community, official Neo4j drivers, and FastAPI/Flask/Express.

---

# 🔐 Environment Variables

Credentials must not be hardcoded into source code or Dockerfiles.

Example `.env`:

```env
NEO4J_DATABASE=CSV_Graph_DB
NEO4J_PASSWORD=csvgraphdb

KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC=csv-rows

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
```

The challenge specifically requires the Neo4j password to be supplied through environment variables rather than hardcoded.

> **Never commit `.env` to GitHub.**

---

# ▶️ How to Run

## 1. Clone repository

```bash
git clone <repository-url>
cd <repository-folder>
```

---

## 2. Configure environment

Create:

```text
.env
```

and provide the required environment variables.

---

## 3. Start the complete stack

```bash
docker compose up --build
```

---

## 4. Check API health

```bash
curl http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok",
  "kafka_connected": true,
  "neo4j_connected": true
}
```

---

## 5. Open the application

Open the frontend in the browser.

The exact frontend URL depends on the Docker Compose port configuration.

---

# 🧪 Testing

Before final submission, test the following.

## Test 1 — Small CSV

Upload a clean CSV containing approximately 10–20 rows.

Verify:

```text
UI
 ↓
API
 ↓
Kafka
 ↓
Loader
 ↓
Neo4j
```

---

## Test 2 — Large CSV

Upload a CSV containing thousands of rows.

Verify that:

* Kafka continues receiving rows
* Loader consumes rows
* Neo4j contains the expected rows
* `/status` reports real progress

---

## Test 3 — Same CSV Twice

Upload the same CSV twice.

Verify:

```text
No duplicate rows
```

This tests `MERGE` and idempotency.

---

## Test 4 — Empty CSV

Expected:

```text
Clean error
```

Not:

```text
500 Internal Server Error
```

---

## Test 5 — Non-CSV

Upload:

```text
example.pdf
```

Expected:

```text
Clean validation error
```

---

## Test 6 — Chat Before Upload

Ask:

```text
How many rows are there?
```

before uploading any CSV.

Expected:

```text
No data available.
grounded: false
```

---

## Test 7 — Valid Chat Question

Upload a CSV and ask a question that can be answered from it.

Verify:

```text
Correct answer
+
Cypher
+
Raw result
+
grounded: true
```

---

## Test 8 — Unsupported Question

Ask something that does not exist in the graph.

Expected:

```text
I don't have enough information in the uploaded data to answer this question.
```

```text
grounded: false
```

---

# 🎬 Demo Flow

The recommended demo should be simple.

## 1. Start system

```bash
docker compose up
```

---

## 2. Show health

Open the UI or API health endpoint.

Show:

```text
Kafka ✓
Neo4j ✓
API ✓
```

---

## 3. Upload CSV

Upload:

```text
customers.csv
```

---

## 4. Show preview

Show the first few rows.

---

## 5. Show progress

Demonstrate:

```text
Total
Loaded
Failed
```

---

## 6. Show Neo4j

Open Neo4j Browser and demonstrate that the rows actually exist.

---

## 7. Ask chatbot

Example:

```text
How many rows are in Billing?
```

---

## 8. Show answer

```text
There are 128 Billing rows.
```

---

## 9. Show Cypher

```cypher
MATCH (r:Row {group: 'Billing'})
RETURN count(r)
```

---

## 10. Show grounded result

```text
✓ Grounded in Neo4j
```

---

## 11. Test duplicate protection

Upload the same CSV again.

Show that duplicate nodes are not created.

---

# 🧠 Design Decisions

## Decision 1 — Kafka between API and Neo4j

### Chosen

```text
API → Kafka → Loader → Neo4j
```

### Rejected

```text
API → Neo4j
```

### Reason

Kafka separates file ingestion from graph loading.

It allows the API to return quickly and allows messages to remain available if Neo4j is temporarily unavailable.

---

## Decision 2 — Generic Dataset/Row graph

### Chosen

```text
Dataset → Row
```

with CSV columns represented as row properties.

### Rejected

A fixed schema designed around one specific CSV.

### Reason

The challenge requires dynamic CSV uploads.

A generic model works with CSVs whose columns are unknown in advance.

---

## Decision 3 — Rule-Based Chatbot

### Chosen

```text
Question
 ↓
Intent
 ↓
Cypher Template
 ↓
Neo4j
```

### Rejected

LLM-based question-to-Cypher generation.

### Reason

The project is designed to work without an external LLM/API dependency while still satisfying the requirement for a natural-language question interface. The challenge explicitly accepts question-to-Cypher template mapping.

---

## Decision 4 — MERGE instead of CREATE

### Chosen

```cypher
MERGE
```

### Rejected

```cypher
CREATE
```

### Reason

`MERGE` makes the loading process idempotent and prevents duplicate rows when the same CSV is loaded again or Kafka messages are replayed.

---

# ⚠️ Startup Readiness

Docker container startup does not necessarily mean the service is ready.

Kafka needs time to elect its leader.

Neo4j may take time before accepting Bolt connections.

Therefore, the system uses either:

```text
healthchecks
+
service_healthy
```

or connection retry logic.

The API and Loader should not assume that Kafka and Neo4j are immediately ready when their containers start.

---

# 🛡️ Container Security

The project follows these requirements:

* Base image versions are pinned.
* `latest` is not used.
* Containers run as non-root users.
* Neo4j credentials come from environment variables.
* Secrets are not hardcoded.
* Images should remain reasonably small.

These are part of the challenge's must-have requirements.

---

# 📊 Project Requirements Checklist

## Core Pipeline

* [x] CSV upload
* [x] API
* [x] Kafka
* [x] `csv-rows` topic
* [x] One Kafka message per CSV row
* [x] Loader
* [x] Neo4j
* [x] Generic Dataset/Row model
* [x] MERGE-based loading

## API

* [x] `POST /ingest`
* [x] `GET /status`
* [x] `GET /health`
* [x] `POST /chat`

## Chatbot

* [x] Natural-language question input
* [x] Rule-based intent detection
* [x] Cypher generation
* [x] Neo4j execution
* [x] Actual result
* [x] Grounded response
* [x] Honest failure response
* [x] Cypher transparency

## UI

* [x] CSV upload
* [x] CSV preview
* [x] Loading status
* [x] Chat interface
* [x] Answer display
* [x] Cypher display

## Reliability

* [x] Idempotent loading
* [x] No duplicate rows
* [x] Real progress
* [x] Health checks
* [x] Startup retry/readiness
* [x] Error handling

## Deployment

* [x] Docker Compose
* [x] Kafka container
* [x] Neo4j container
* [x] API container
* [x] Loader container
* [x] UI container
* [x] Pinned image versions
* [x] Non-root containers
* [x] Environment-based credentials

---

# 🚨 Pre-Freeze Checklist

Before final submission:

```text
[ ] docker compose down -v
[ ] docker compose up works from a clean state
[ ] No `latest` Docker image tags
[ ] Neo4j password comes from environment variables
[ ] Containers run as non-root
[ ] Kafka is genuinely reachable before /health becomes OK
[ ] Neo4j is genuinely reachable before /health becomes OK
[ ] /status contains real row counts
[ ] /status includes failures
[ ] Empty CSV handled
[ ] Non-CSV handled
[ ] Chat before upload handled
[ ] Same CSV uploaded twice without duplicates
[ ] Chatbot returns Cypher
[ ] Chatbot returns raw result
[ ] Chatbot uses grounded=true only when supported by graph data
[ ] Unsupported questions return grounded=false
[ ] REPORT.md completed
[ ] Everything committed
[ ] Everything pushed
```

The official handout recommends this exact type of pre-freeze verification before submission.

---

# 📈 Future Improvements

Possible future improvements include:

### 1. Foreign-Key Detection

Automatically detect columns that look like IDs and create actual graph relationships.

Example:

```text
Customer
   |
PLACED
   |
Order
```

instead of storing everything as flat properties.

---

### 2. Advanced Chatbot

Support more natural question variations.

---

### 3. More Analytics

Add:

* Group summaries
* Numeric statistics
* Distribution analysis
* Data-quality reports

---

### 4. Better Progress Tracking

Provide real-time ingestion progress for large datasets.

---

### 5. Duplicate Dataset Detection

Detect whether a previously uploaded file is the same file or a modified version with the same filename.

---

# ⚠️ Current Limitations

The current chatbot is deterministic and template-based.

Therefore, it does not understand unlimited forms of natural language.

For example:

```text
"How many records are there?"
```

may be supported.

But a very complex question with unusual wording may not be recognized.

This is an intentional trade-off to keep the system:

* Fast
* Deterministic
* Easy to test
* Independent of external LLM APIs
* Grounded in Neo4j

---

# 🏁 Why This Architecture?

The project is not only about creating a chatbot.

The main objective is to demonstrate a complete, reliable data pipeline:

```text
              DATA
               ↓
             CSV
               ↓
              API
               ↓
             Kafka
               ↓
             Loader
               ↓
             Neo4j
               ↓
          Query Engine
               ↓
            Chatbot
               ↓
             ANSWER
```

The chatbot is only one part of the system.

A reliable pipeline, correct Kafka architecture, idempotent loading, real status reporting, honest health checks, and a grounded chatbot are the main engineering goals.

The challenge's marking scheme reflects this: chatbot groundedness is 10 marks, while the remaining marks focus heavily on the pipeline, Docker, API, idempotency, health, and report.

---

# 👥 Team

| Member        | Responsibility            |
| ------------- | ------------------------- |
| Team Member 1 | UI / Frontend             |
| Team Member 2 | API / Backend             |
| Team Member 3 | Kafka / Loader            |
| Team Member 4 | Neo4j / Chatbot / Testing |

Update this section with the actual team members and responsibilities.

---

# 📚 Reference

This implementation is based on the **Data In, Answers Out — Build a CSV → Kafka → Neo4j Chatbot Pipeline** hackathon handout.

The required architecture, API contracts, Kafka topic, Neo4j model, idempotency requirements, chatbot grounding rules, Docker requirements, testing strategy, timeline, and scoring criteria are derived from the official handout.

---

# ❤️ Final Principle

> **Build the pipe first.**

A simple chatbot on top of a reliable:

```text
CSV → Kafka → Neo4j
```

pipeline is more valuable than a complicated chatbot sitting on a broken system.

**Data In → Graph → Answers Out.**
