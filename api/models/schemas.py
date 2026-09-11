from typing import Any, Optional
from pydantic import BaseModel


class IngestResponse(BaseModel):
    job_id: str
    rows_received: int
    status: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    rows_total: int
    rows_loaded: int
    rows_failed: int
    filename: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    kafka_connected: bool
    neo4j_connected: bool


class ChatRequest(BaseModel):
    question: str
    job_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    cypher: str
    result: list[dict[str, Any]]
    grounded: bool
