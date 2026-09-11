from fastapi import APIRouter, HTTPException

from models.schemas import StatusResponse
from services.neo4j_service import neo4j_service

router = APIRouter()


@router.get("/status", response_model=StatusResponse)
async def get_status(job_id: str):
    data = neo4j_service.get_dataset_status(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No dataset found for this job_id.")
    return StatusResponse(job_id=job_id, **data)
