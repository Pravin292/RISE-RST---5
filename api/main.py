import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Safety net: no endpoint should ever surface a bare, un-JSON crash page.
    # Any bug we haven't anticipated still comes back as a clean 500 with a
    # readable message instead of Starlette's plain-text default response.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Unexpected server error: {exc}"},
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
