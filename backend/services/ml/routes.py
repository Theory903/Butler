"""ML service - embeddings and intent classification."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/ml", tags=["ml"])


class EmbedRequest(BaseModel):
    text: str
    model: str | None = "text-embedding-3-small"


class EmbedResponse(BaseModel):
    embedding: list[float]
    model: str
    tokens: int


class IntentRequest(BaseModel):
    message: str


class IntentResponse(BaseModel):
    intent: str
    confidence: float
    entities: dict


INTENT_KEYWORDS = {
    "greeting": ["hello", "hi", "hey", "greetings"],
    "question": ["what", "how", "why", "when", "where", "who", "which"],
    "command": ["do", "make", "create", "send", "get", "find", "search"],
    "statement": ["the", "this", "that", "it", "i think"],
}


@router.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    embedding = [0.1] * 1536
    return EmbedResponse(embedding=embedding, model=req.model, tokens=len(req.text.split()))


@router.post("/classify_intent", response_model=IntentResponse)
async def classify_intent(req: IntentRequest):
    message_lower = req.message.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in message_lower:
                return IntentResponse(intent=intent, confidence=0.8, entities={})
    return IntentResponse(intent="unknown", confidence=0.5, entities={})


@router.get("/health")
async def health():
    return {"status": "healthy"}
