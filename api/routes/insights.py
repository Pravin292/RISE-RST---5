from fastapi import APIRouter, HTTPException

from services.neo4j_service import neo4j_service

router = APIRouter()


@router.get("/insights")
async def insights(job_id: str):
    data = neo4j_service.get_insights(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No dataset found for this job_id.")
    return data


@router.get("/graph")
async def graph(job_id: str, limit: int = 40):
    data = neo4j_service.get_graph_sample(job_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="No dataset found for this job_id.")
    return data
