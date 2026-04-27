import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.routes.gateway import get_current_account

# Dependency injection for routing
from core.deps import get_tools_service
from domain.auth.contracts import AccountContext
from domain.runtime.context import RuntimeContext
from services.tools.executor import ToolExecutionRequest, ToolExecutor

router = APIRouter(prefix="/tools", tags=["tools"])


class ExecuteToolRequest(BaseModel):
    params: dict
    idempotency_key: str | None = None


@router.get("/")
async def list_tools(category: str | None = None, svc: ToolExecutor = Depends(get_tools_service)):
    return await svc.list_tools(category)


@router.post("/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    req: ExecuteToolRequest,
    account: AccountContext = Depends(get_current_account),
    svc: ToolExecutor = Depends(get_tools_service),
):
    # Build RuntimeContext for canonical execution
    # Note: tenant_id is not yet in AccountContext, using account_id as fallback
    # This should be updated once multi-tenant is fully implemented
    request_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())

    context = RuntimeContext.create(
        tenant_id=account.aid,  # Using aid as tenant_id for now
        account_id=account.account_id,
        session_id=account.session_id,
        request_id=request_id,
        trace_id=trace_id,
        channel="api",
        user_id=account.sub,  # Using sub as user_id
        device_id=account.device_id,
    )

    # Use canonical execution path
    exec_request = ToolExecutionRequest(
        tool_name=tool_name,
        input=req.params,  # ToolExecutionRequest uses 'input' not 'params'
        context=context,
        idempotency_key=req.idempotency_key,
    )

    return await svc.execute_canonical(exec_request)
