from fastapi import APIRouter

from models.schemas import ChatRequest, ChatResponse
from services.chatbot import answer_question
from services.neo4j_service import neo4j_service

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    dataset_id = payload.job_id or neo4j_service.get_latest_dataset_id()
    result = answer_question(payload.question, dataset_id)
    return ChatResponse(**result)
