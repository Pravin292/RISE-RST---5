import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import chat, health, ingest, insights, status
from services.kafka_producer import producer_service
from services.neo4j_service import neo4j_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="CSV -> Kafka -> Neo4j Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(status.router)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(insights.router)


@app.on_event("startup")
async def on_startup():
    logger.info("API starting up, waiting for Kafka and Neo4j ...")
    producer_service.wait_until_ready()
    neo4j_service.wait_until_ready()
    logger.info("Startup checks complete.")


@app.on_event("shutdown")
async def on_shutdown():
    neo4j_service.close()
