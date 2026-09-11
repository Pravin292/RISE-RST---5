from fastapi import APIRouter
from services.kafka_producer import kafka_service
from services.neo4j_service import neo4j_service

router = APIRouter()

@router.get("/health")
def get_health():
    kafka_ok = kafka_service.check_health()
    neo4j_ok = neo4j_service.check_health()
    
    is_healthy = kafka_ok and neo4j_ok
    status_str = "ok" if is_healthy else "degraded"
    
    return {
        "status": status_str,
        "kafka_connected": kafka_ok,
        "neo4j_connected": neo4j_ok
    }
