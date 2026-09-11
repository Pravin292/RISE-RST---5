from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from services.neo4j_service import neo4j_service

router = APIRouter()

@router.get("/status")
def get_status(job_id: Optional[str] = Query(None)):
    if job_id:
        job = neo4j_service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        return job
    
    # If no job_id provided, return latest job
    query = """
    MATCH (j:Job)
    RETURN j.job_id AS job_id, j.status AS status, j.rows_total AS rows_total, 
           j.rows_loaded AS rows_loaded, j.rows_failed AS rows_failed
    ORDER BY j.created_at DESC
    LIMIT 1
    """
    try:
        records = neo4j_service.execute_cypher(query)
        if records:
            return records[0]
        return {
            "job_id": None,
            "status": "idle",
            "rows_total": 0,
            "rows_loaded": 0,
            "rows_failed": 0
        }
    except Exception as e:
        return {
            "job_id": None,
            "status": "idle",
            "rows_total": 0,
            "rows_loaded": 0,
            "rows_failed": 0
        }
