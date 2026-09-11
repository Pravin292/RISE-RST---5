from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.chatbot import chatbot_engine

router = APIRouter()

class ChatRequest(BaseModel):
    question: str

@router.post("/chat")
def chat_endpoint(request: ChatRequest):
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
        
    result = chatbot_engine.process_question(request.question)
    return result
