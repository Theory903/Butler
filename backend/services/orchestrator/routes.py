"""Orchestrator service - intent parsing, planning, execution."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str


class ChatResponse(BaseModel):
    response: str
    intent: str
    session_id: str
    request_id: str


@router.post("/process", response_model=ChatResponse)
async def process(request: ChatRequest):
    intent = classify_intent(request.message)
    response = generate_response(request.message, intent)
    return ChatResponse(
        response=response,
        intent=intent,
        session_id=request.session_id,
        request_id=f"req_{request.session_id[:8]}",
    )


def classify_intent(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ["hello", "hi", "hey"]):
        return "greeting"
    if any(w in msg for w in ["what", "how", "why", "when"]):
        return "question"
    if any(w in msg for w in ["search", "find", "look"]):
        return "search"
    if any(w in msg for w in ["send", "create", "do", "make"]):
        return "command"
    return "statement"


def generate_response(message: str, intent: str) -> str:
    responses = {
        "greeting": "Hi! How can I help you today?",
        "question": "That's a great question. Let me help you with that.",
        "search": "I'll search for that information for you.",
        "command": "I'll take care of that for you.",
        "statement": "I understand. What would you like me to do?",
    }
    return responses.get(intent, "I'm here to help.")


@router.get("/health")
async def health():
    return {"status": "healthy"}