from fastapi import APIRouter

from models.schemas import HealthResponse
from services.kafka_producer import producer_service
from services.neo4j_service import neo4j_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    kafka_ok = producer_service.is_connected()
    neo4j_ok = neo4j_service.is_connected()
    return HealthResponse(
        status="ok" if (kafka_ok and neo4j_ok) else "degraded",
        kafka_connected=kafka_ok,
        neo4j_connected=neo4j_ok,
    )
