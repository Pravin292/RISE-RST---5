import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.health import router as health_router
from routes.ingest import router as ingest_router
from routes.status import router as status_router
from routes.chat import router as chat_router
from services.neo4j_service import neo4j_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_api")

app = FastAPI(
    title="CSV → Kafka → Neo4j Chatbot Pipeline API",
    description="Deterministic rule-based graph chatbot pipeline API",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health_router, tags=["Health"])
app.include_router(ingest_router, tags=["Ingestion"])
app.include_router(status_router, tags=["Status"])
app.include_router(chat_router, tags=["Chatbot"])

@app.get("/")
def root():
    return {
        "message": "CSV → Kafka → Neo4j Pipeline API is running",
        "health": "/health",
        "docs": "/docs"
    }

@app.get("/schema")
def get_schema():
    properties = neo4j_service.get_active_row_properties()
    count = neo4j_service.get_active_row_count()
    return {
        "active_row_count": count,
        "properties": properties
    }
