"""Memory service - session storage, context retrieval."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from infrastructure.cache import redis_client

router = APIRouter(prefix="/memory", tags=["memory"])


class MessageInput(BaseModel):
    role: str
    content: str
    timestamp: datetime | None = None


class SessionCreate(BaseModel):
    session_id: str


@router.post("/sessions")
async def create_session(session_id: str):
    redis = redis_client.client
    key = f"session:{session_id}"
    await redis.delete(key)
    return {"session_id": session_id, "created": True}


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, message: MessageInput):
    redis = redis_client.client
    key = f"session:{session_id}"
    msg_data = {
        "role": message.role,
        "content": message.content,
        "timestamp": (message.timestamp or datetime.now(UTC)).isoformat(),
    }
    await redis.rpush(key, json.dumps(msg_data))
    return {"added": True}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, limit: int = 100):
    redis = redis_client.client
    key = f"session:{session_id}"
    messages = await redis.lrange(key, -limit, -1)
    return {"messages": [json.loads(m) for m in messages]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    redis = redis_client.client
    await redis.delete(f"session:{session_id}")
    return {"deleted": True}


@router.get("/health")
async def health():
    return {"status": "healthy"}
