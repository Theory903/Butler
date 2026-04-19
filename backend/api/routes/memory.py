import uuid
from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Optional, List
from pydantic import BaseModel

from domain.auth.contracts import AccountContext
from api.routes.gateway import get_current_account
from services.memory.service import MemoryService
from core.deps import get_db, get_redis
from infrastructure.config import settings

# ── Dynamic Service Injection ────────────────────────────────────────────────

from core.deps import get_db, get_cache as get_redis, get_memory_service

# ── API Router ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/memory", tags=["memory"])

class StoreMemoryRequest(BaseModel):
    memory_type: str
    content: dict
    kwargs: dict = {}

class RecallRequest(BaseModel):
    query: str
    memory_types: Optional[List[str]] = None
    limit: int = 20

class ContextRequest(BaseModel):
    query: str
    session_id: str

@router.post("/store")
async def store_memory(
    req: StoreMemoryRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service)
):
    """Store a memory with automatic evolution and understanding."""
    return await svc.store(str(account.account_id), req.memory_type, req.content, **req.kwargs)

@router.post("/recall")
async def recall(
    req: RecallRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service)
):
    """Hybrid weighted retrieval across all backends."""
    return await svc.recall(str(account.account_id), req.query, req.memory_types, req.limit)

@router.post("/context", response_model=Any)
async def get_context_pack(
    req: ContextRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service)
) -> Any:
    """Get high-fidelity ContextPack for model generation."""
    return await svc.build_context(str(account.account_id), req.query, req.session_id)

@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: str,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service)
):
    """Trigger episodic capture for a session."""
    return await svc.end_session(str(account.account_id), session_id)

@router.get("/profile")
async def get_user_profile(
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service)
):
    """Fetch user preferences and constraints."""
    # Logic to return compiled preference JSON
    return {"account_id": account.account_id, "meta": "oracle_grade_v2"}
