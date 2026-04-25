from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.routes.gateway import get_current_account

# ── Dynamic Service Injection ────────────────────────────────────────────────
from core.deps import get_memory_service
from domain.auth.contracts import AccountContext
from services.memory.service import MemoryService

# ── API Router ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/memory", tags=["memory"])


def _serialize_memory_entry(entry: Any) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "account_id": str(entry.account_id),
        "memory_type": entry.memory_type,
        "content": entry.content,
        "importance": entry.importance,
        "confidence": entry.confidence,
        "source": entry.source,
        "session_id": entry.session_id,
        "tags": entry.tags,
        "status": entry.status.value if hasattr(entry.status, "value") else str(entry.status),
        "metadata": entry.metadata_col,
        "valid_from": entry.valid_from.isoformat() if entry.valid_from else None,
        "valid_until": entry.valid_until.isoformat() if entry.valid_until else None,
        "superseded_by": str(entry.superseded_by) if entry.superseded_by else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "last_accessed_at": entry.last_accessed_at.isoformat() if entry.last_accessed_at else None,
        "access_count": entry.access_count,
    }


class StoreMemoryRequest(BaseModel):
    memory_type: str
    content: dict
    kwargs: dict = {}


class RecallRequest(BaseModel):
    query: str
    memory_types: list[str] | None = None
    limit: int = 20


class ContextRequest(BaseModel):
    query: str
    session_id: str


@router.post("/store")
async def store_memory(
    req: StoreMemoryRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service),
):
    """Store a memory with automatic evolution and understanding."""
    entry = await svc.store(
        account_id=str(account.account_id),
        memory_type=req.memory_type,
        content=req.content,
        tenant_id=account.tenant_id,
        **req.kwargs,
    )
    return _serialize_memory_entry(entry)


@router.post("/recall")
async def recall(
    req: RecallRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service),
):
    """Hybrid weighted retrieval across all backends."""
    entries = await svc.recall(
        account_id=str(account.account_id),
        query=req.query,
        memory_types=req.memory_types or [],
        limit=req.limit,
        tenant_id=account.tenant_id,
    )
    return [_serialize_memory_entry(entry) for entry in entries]


@router.post("/context", response_model=Any)
async def get_context_pack(
    req: ContextRequest,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service),
) -> Any:
    """Get high-fidelity ContextPack for model generation."""
    return await svc.build_context(
        account_id=str(account.account_id),
        query=req.query,
        session_id=req.session_id,
        tenant_id=account.tenant_id,
    )


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: str,
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service),
):
    """Trigger episodic capture for a session."""
    return await svc.end_session(str(account.account_id), session_id, tenant_id=account.tenant_id)


@router.get("/profile")
async def get_user_profile(
    account: AccountContext = Depends(get_current_account),
    svc: MemoryService = Depends(get_memory_service),
):
    """Fetch user preferences and constraints."""
    # Logic to return compiled preference JSON
    return {"account_id": account.account_id, "meta": "oracle_grade_v2"}
