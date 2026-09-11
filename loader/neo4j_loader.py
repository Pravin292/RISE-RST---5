import os
import time
import logging
from typing import Dict, Any
from neo4j import GraphDatabase, Driver

logger = logging.getLogger("neo4j_loader")
logging.basicConfig(level=logging.INFO)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "csvgraphdb")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "CSV_Graph_DB")

class Neo4jLoader:
    def __init__(self):
        self.driver: Driver = None
        self._connect_with_retry()

    def _connect_with_retry(self, max_retries=30, delay=2):
        for attempt in range(1, max_retries + 1):
            try:
                self.driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USER, NEO4J_PASSWORD)
                )
                with self.driver.session(database=NEO4J_DATABASE) as session:
                    session.run("RETURN 1")
                logger.info("Successfully connected to Neo4j in Loader.")
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_retries} - Neo4j not ready in Loader: {e}")
                time.sleep(delay)
        raise RuntimeError("Could not connect to Neo4j after multiple retries.")

    def close(self):
        if self.driver:
            self.driver.close()

    def load_row(self, dataset_id: str, filename: str, row_index: int, row_data: Dict[str, Any], uploaded_at: str) -> bool:
        row_id = f"{dataset_id}_{row_index}"
        
        # Clean row data: convert None or nan values
        clean_props = {}
        for k, v in row_data.items():
            if v is not None and str(v).lower() != "nan":
                clean_props[str(k)] = v

        cypher = """
        MERGE (d:Dataset {id: $dataset_id})
        ON CREATE SET d.filename = $filename, d.uploaded_at = $uploaded_at

        MERGE (r:Row {id: $row_id})
        SET r.dataset_id = $dataset_id,
            r.row_index = $row_index
        SET r += $clean_props

        MERGE (d)-[:HAS_ROW]->(r)
        """

        try:
            with self.driver.session(database=NEO4J_DATABASE) as session:
                session.run(
                    cypher,
                    dataset_id=dataset_id,
                    filename=filename,
                    uploaded_at=uploaded_at,
                    row_id=row_id,
                    row_index=row_index,
                    clean_props=clean_props
                )
            self._update_job_progress(dataset_id=dataset_id, success=True)
            return True
        except Exception as e:
            logger.error(f"Failed to MERGE row {row_index} for dataset {dataset_id}: {e}")
            self._update_job_progress(dataset_id=dataset_id, success=False)
            return False

    def _update_job_progress(self, dataset_id: str, success: bool):
        # Extract job_id from dataset_id ("dataset_abc123" -> "abc123")
        job_id = dataset_id.replace("dataset_", "")
        
        update_query = """
        MATCH (j:Job {job_id: $job_id})
        SET j.rows_loaded = j.rows_loaded + (CASE WHEN $success THEN 1 ELSE 0 END),
            j.rows_failed = j.rows_failed + (CASE WHEN $success THEN 0 ELSE 1 END),
            j.status = 'loading'
        WITH j
        SET j.status = CASE 
            WHEN j.rows_loaded + j.rows_failed >= j.rows_total THEN 'complete'
            ELSE 'loading'
        END
        RETURN j.status AS current_status, j.rows_loaded AS loaded, j.rows_total AS total
        """
        try:
            with self.driver.session(database=NEO4J_DATABASE) as session:
                session.run(update_query, job_id=job_id, success=success)
        except Exception as e:
            logger.error(f"Error updating job progress for job {job_id}: {e}")

neo4j_loader = Neo4jLoader()
