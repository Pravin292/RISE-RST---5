import logging
import os
import time

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

logger = logging.getLogger("api.neo4j")

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "csvgraphdb")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "CSV_Graph_DB")


class Neo4jService:
    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def close(self) -> None:
        self._driver.close()

    def is_connected(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j health check failed: %s", exc)
            return False

    def wait_until_ready(self, timeout_seconds: int = 90) -> None:
        deadline = time.time() + timeout_seconds
        last_exc = None
        while time.time() < deadline:
            try:
                self._driver.verify_connectivity()
                logger.info("Neo4j is reachable at %s", NEO4J_URI)
                self._ensure_constraints()
                return
            except (ServiceUnavailable, Exception) as exc:  # noqa: BLE001
                last_exc = exc
                logger.info("Waiting for Neo4j ...")
                time.sleep(2)
        logger.warning("Neo4j not reachable after %ss (%s), continuing anyway", timeout_seconds, last_exc)

    def _ensure_constraints(self) -> None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS "
                "FOR (d:Dataset) REQUIRE d.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT row_key_unique IF NOT EXISTS "
                "FOR (r:Row) REQUIRE r.row_key IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT failed_row_key_unique IF NOT EXISTS "
                "FOR (f:FailedRow) REQUIRE f.row_key IS UNIQUE"
            )

    def create_dataset(self, dataset_id: str, filename: str, uploaded_at: str, total_rows: int, columns: list[str]) -> None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                """
                MERGE (d:Dataset {id: $id})
                ON CREATE SET d.uploaded_at = $uploaded_at, d.status = 'queued'
                SET d.filename = $filename,
                    d.total_rows = $total_rows,
                    d.columns = $columns
                """,
                id=dataset_id,
                filename=filename,
                uploaded_at=uploaded_at,
                total_rows=total_rows,
                columns=columns,
            )

    def get_dataset_status(self, dataset_id: str) -> dict | None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                """
                MATCH (d:Dataset {id: $id})
                OPTIONAL MATCH (d)-[:HAS_ROW]->(r:Row)
                OPTIONAL MATCH (f:FailedRow {dataset_id: $id})
                RETURN d.filename AS filename, d.total_rows AS total_rows,
                       count(DISTINCT r) AS rows_loaded, count(DISTINCT f) AS rows_failed
                """,
                id=dataset_id,
            ).single()
            if record is None:
                return None
            data = dict(record)
            rows_total = data["total_rows"] or 0
            rows_loaded = data["rows_loaded"] or 0
            rows_failed = data["rows_failed"] or 0
            if rows_loaded + rows_failed >= rows_total and rows_total > 0:
                status = "complete"
            elif rows_loaded > 0 or rows_failed > 0:
                status = "loading"
            else:
                status = "queued"
            return {
                "filename": data["filename"],
                "rows_total": rows_total,
                "rows_loaded": rows_loaded,
                "rows_failed": rows_failed,
                "status": status,
            }

    def get_latest_dataset_id(self) -> str | None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                "MATCH (d:Dataset) RETURN d.id AS id ORDER BY d.uploaded_at DESC LIMIT 1"
            ).single()
            return record["id"] if record else None

    def dataset_exists(self, dataset_id: str) -> bool:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                "MATCH (d:Dataset {id: $id}) RETURN d.id AS id", id=dataset_id
            ).single()
            return record is not None

    def get_columns(self, dataset_id: str) -> list[str]:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            record = session.run(
                "MATCH (d:Dataset {id: $id}) RETURN d.columns AS columns", id=dataset_id
            ).single()
            return record["columns"] if record and record["columns"] else []

    def run_read(self, cypher: str, **params) -> list[dict]:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(cypher, **params)
            return [dict(r) for r in result]

    def get_insights(self, dataset_id: str) -> dict | None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            ds = session.run(
                "MATCH (d:Dataset {id: $id}) RETURN d.columns AS columns, d.total_rows AS total_rows, d.filename AS filename",
                id=dataset_id,
            ).single()
            if ds is None:
                return None
            columns = ds["columns"] or []
            total_rows = ds["total_rows"] or 0

            row_count_rec = session.run(
                "MATCH (:Dataset {id: $id})-[:HAS_ROW]->(r:Row) RETURN count(r) AS c",
                id=dataset_id,
            ).single()
            loaded_rows = row_count_rec["c"] if row_count_rec else 0

            column_stats = []
            for col in columns:
                stat = session.run(
                    f"""
                    MATCH (:Dataset {{id: $id}})-[:HAS_ROW]->(r:Row)
                    WITH r, r.`{col}` AS val
                    RETURN count(r) AS total,
                           count(CASE WHEN val IS NULL OR val = '' THEN 1 END) AS missing,
                           count(DISTINCT val) AS unique_count
                    """,
                    id=dataset_id,
                ).single()
                total = stat["total"] or 0
                missing = stat["missing"] or 0
                column_stats.append({
                    "column": col,
                    "missing": missing,
                    "missing_pct": round((missing / total) * 100, 1) if total else 0,
                    "unique_count": stat["unique_count"] or 0,
                })

            avg_missing_pct = (
                sum(c["missing_pct"] for c in column_stats) / len(column_stats)
                if column_stats else 0
            )
            completeness_score = max(0.0, 100.0 - avg_missing_pct)
            loaded_ratio = (loaded_rows / total_rows) if total_rows else 0
            health_score = round((completeness_score * 0.7) + (loaded_ratio * 100 * 0.3), 1)

            suggestions = ["How many rows are there?"]
            if columns:
                suggestions.append(f"What are the unique values of {columns[0]}?")
                for col in columns:
                    if col in ("age", "amount", "price", "quantity", "score", "salary", "total"):
                        suggestions.append(f"What is the average {col}?")
                        suggestions.append(f"What is the maximum {col}?")
                        break

            return {
                "dataset_id": dataset_id,
                "filename": ds["filename"],
                "rows_total": total_rows,
                "rows_loaded": loaded_rows,
                "health_score": health_score,
                "columns": column_stats,
                "suggested_questions": suggestions[:5],
            }

    def get_graph_sample(self, dataset_id: str, limit: int = 40) -> dict | None:
        with self._driver.session(database=NEO4J_DATABASE) as session:
            ds = session.run(
                "MATCH (d:Dataset {id: $id}) RETURN d.id AS id, d.filename AS filename",
                id=dataset_id,
            ).single()
            if ds is None:
                return None
            rows = session.run(
                """
                MATCH (d:Dataset {id: $id})-[:HAS_ROW]->(r:Row)
                RETURN r.row_key AS id, r.row_index AS row_index, properties(r) AS props
                ORDER BY r.row_index ASC
                LIMIT $limit
                """,
                id=dataset_id,
                limit=limit,
            )
            nodes = [{"id": ds["id"], "type": "Dataset", "label": ds["filename"]}]
            edges = []
            for r in rows:
                nodes.append({"id": r["id"], "type": "Row", "label": f"Row {r['row_index']}", "props": r["props"]})
                edges.append({"source": ds["id"], "target": r["id"]})
            return {"nodes": nodes, "edges": edges}


neo4j_service = Neo4jService()
