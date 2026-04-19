from fastapi import APIRouter, Depends
from typing import Optional
from pydantic import BaseModel

from domain.auth.contracts import AccountContext
from api.routes.gateway import get_current_account
from services.tools.executor import ToolExecutor
from services.tools.verification import ToolVerifier
from core.deps import get_db, get_redis

# Dependency injection for routing
from core.deps import get_db, get_cache as get_redis, get_tools_service

router = APIRouter(prefix="/tools", tags=["tools"])

class ExecuteToolRequest(BaseModel):
    params: dict
    idempotency_key: Optional[str] = None

@router.get("/")
async def list_tools(category: Optional[str] = None, svc: ToolExecutor = Depends(get_tools_service)):
    return await svc.list_tools(category)

@router.post("/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    req: ExecuteToolRequest,
    account: AccountContext = Depends(get_current_account),
    svc: ToolExecutor = Depends(get_tools_service)
):
    return await svc.execute(
        tool_name=tool_name,
        params=req.params,
        account_id=str(account.account_id),
        idempotency_key=req.idempotency_key
    )
