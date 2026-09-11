import logging
import os
import time

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

logger = logging.getLogger("loader.neo4j")

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "csvgraphdb")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "CSV_Graph_DB")


class Neo4jLoader:
    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def wait_until_ready(self, timeout_seconds: int = 120) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                self._driver.verify_connectivity()
                logger.info("Neo4j is reachable at %s", NEO4J_URI)
                return
            except (ServiceUnavailable, Exception) as exc:  # noqa: BLE001
                logger.info("Waiting for Neo4j ... (%s)", exc)
                time.sleep(2)
        raise RuntimeError("Neo4j never became reachable")

    def close(self) -> None:
        self._driver.close()

    def merge_row(self, dataset_id: str, filename: str, uploaded_at: str, total_rows: int,
                  columns: list[str], row_index: int, row: dict) -> None:
        row_key = f"{dataset_id}_{row_index}"
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.execute_write(self._merge_row_tx, dataset_id, filename, uploaded_at,
                                   total_rows, columns, row_key, row_index, row)

    @staticmethod
    def _merge_row_tx(tx, dataset_id, filename, uploaded_at, total_rows, columns, row_key, row_index, row):
        tx.run(
            """
            MERGE (d:Dataset {id: $dataset_id})
            ON CREATE SET d.filename = $filename,
                          d.uploaded_at = $uploaded_at,
                          d.total_rows = $total_rows,
                          d.columns = $columns,
                          d.status = 'loading'
            SET d.status = CASE WHEN d.status = 'queued' THEN 'loading' ELSE d.status END
            WITH d
            MERGE (r:Row {row_key: $row_key})
            SET r += $row,
                r.row_index = $row_index,
                r.dataset_id = $dataset_id
            MERGE (d)-[:HAS_ROW]->(r)
            """,
            dataset_id=dataset_id,
            filename=filename,
            uploaded_at=uploaded_at,
            total_rows=total_rows,
            columns=columns,
            row_key=row_key,
            row_index=row_index,
            row=row,
        )

    def mark_row_failed(self, dataset_id: str, row_index: int, error: str, raw: str) -> None:
        row_key = f"{dataset_id}_{row_index}"
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                """
                MERGE (f:FailedRow {row_key: $row_key})
                SET f.dataset_id = $dataset_id,
                    f.row_index = $row_index,
                    f.error = $error,
                    f.raw = $raw
                """,
                row_key=row_key,
                dataset_id=dataset_id,
                row_index=row_index,
                error=error,
                raw=raw,
            )
