import os
import time
import logging
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver

logger = logging.getLogger("neo4j_service")
logging.basicConfig(level=logging.INFO)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "csvgraphdb")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "CSV_Graph_DB")

class Neo4jService:
    def __init__(self):
        self.driver: Optional[Driver] = None
        self._connect()

    def _connect(self):
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            logger.info("Neo4j driver initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def check_health(self) -> bool:
        if not self.driver:
            self._connect()
        if not self.driver:
            return False
        try:
            with self.driver.session(database=NEO4J_DATABASE) as session:
                result = session.run("RETURN 1 AS result")
                record = result.single()
                return record is not None and record["result"] == 1
        except Exception as e:
            logger.warning(f"Neo4j healthcheck failed: {e}")
            # Try default database fallback if specified db fails
            try:
                with self.driver.session() as session:
                    result = session.run("RETURN 1 AS result")
                    record = result.single()
                    return record is not None and record["result"] == 1
            except Exception as inner_e:
                logger.error(f"Neo4j fallback healthcheck failed: {inner_e}")
                return False

    def create_job(self, job_id: str, filename: str, rows_total: int) -> Dict[str, Any]:
        query = """
        MERGE (j:Job {job_id: $job_id})
        SET j.filename = $filename,
            j.rows_total = $rows_total,
            j.rows_loaded = 0,
            j.rows_failed = 0,
            j.status = 'queued',
            j.created_at = datetime()
        RETURN j
        """
        with self.driver.session(database=NEO4J_DATABASE) as session:
            session.run(query, job_id=job_id, filename=filename, rows_total=rows_total)
        return {
            "job_id": job_id,
            "filename": filename,
            "rows_total": rows_total,
            "rows_loaded": 0,
            "rows_failed": 0,
            "status": "queued"
        }

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        query = """
        MATCH (j:Job {job_id: $job_id})
        RETURN j.job_id AS job_id, j.status AS status, j.rows_total AS rows_total, 
               j.rows_loaded AS rows_loaded, j.rows_failed AS rows_failed
        """
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, job_id=job_id)
            record = result.single()
            if record:
                return {
                    "job_id": record["job_id"],
                    "status": record["status"],
                    "rows_total": record["rows_total"],
                    "rows_loaded": record["rows_loaded"],
                    "rows_failed": record["rows_failed"]
                }
            return None

    def execute_cypher(self, cypher_query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.driver:
            self._connect()
        if params is None:
            params = {}
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(cypher_query, **params)
            return [record.data() for record in result]

    def get_active_row_properties(self) -> List[str]:
        query = """
        MATCH (r:Row)
        WITH keys(r) AS k
        UNWIND k AS key
        WITH DISTINCT key
        WHERE NOT key IN ['id', 'row_index', 'dataset_id']
        RETURN key
        """
        try:
            records = self.execute_cypher(query)
            return [r["key"] for r in records if "key" in r]
        except Exception as e:
            logger.error(f"Error fetching active row properties: {e}")
            return []

    def get_active_row_count(self) -> int:
        query = "MATCH (r:Row) RETURN count(r) AS total"
        try:
            records = self.execute_cypher(query)
            if records and "total" in records[0]:
                return records[0]["total"]
            return 0
        except Exception as e:
            logger.error(f"Error fetching active row count: {e}")
            return 0

neo4j_service = Neo4jService()
