from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.routes.gateway import get_current_account
from domain.auth.contracts import AccountContext
from domain.security.models import ActorContext, PolicyInput, ToolGateRequest
from services.security import SecurityService


def get_security() -> SecurityService:
    return SecurityService()


router = APIRouter(prefix="/security", tags=["security"])


class AuthorizeRequest(BaseModel):
    action: str
    content_trust_level: str
    assurance_level: str
    approval_state: str

    def to_policy_input(self) -> PolicyInput:
        return PolicyInput(**self.dict())


class ContentEvalRequest(BaseModel):
    content: str
    source: str


class ToolValidateRequest(BaseModel):
    scope: str
    approval_token: str = None
    idempotency_key: str = None


@router.post("/authorize")
async def authorize(req: AuthorizeRequest, svc: SecurityService = Depends(get_security)):
    decision = await svc.evaluate_policy(req.to_policy_input())
    return {
        "allowed": decision.allow,
        "reason": decision.reason,
        "obligations": decision.obligations,
    }


@router.post("/content/evaluate")
async def evaluate_content(req: ContentEvalRequest, svc: SecurityService = Depends(get_security)):
    decision = await svc.evaluate_content(req.content, req.source)
    return decision.dict()


@router.post("/tool/validate")
async def validate_tool(
    req: ToolValidateRequest,
    account: AccountContext = Depends(get_current_account),
    svc: SecurityService = Depends(get_security),
):
    actor = ActorContext(account_id=str(account.account_id))
    gate_req = ToolGateRequest(**req.dict())
    decision = await svc.validate_tool_request(gate_req, actor)
    return {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "requires_approval": decision.requires_approval,
    }
