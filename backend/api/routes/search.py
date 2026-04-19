from fastapi import APIRouter, Depends
from pydantic import BaseModel

from domain.auth.contracts import AccountContext
from api.routes.gateway import get_current_account
from services.search.service import SearchService
from services.search.extraction import ContentExtractor

# Dependency injection for routing
async def get_search_service() -> SearchService:
    extractor = ContentExtractor()
    return SearchService(extractor)

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    mode: str = "auto"

@router.post("/")
async def search(
    req: SearchRequest,
    account: AccountContext = Depends(get_current_account),
    svc: SearchService = Depends(get_search_service)
):
    # Depending on architecture, we might just return the Pydantic dict representation of EvidencePack
    # Since EvidencePack is a dataclass, we can return it safely with FastAPI
    return await svc.search(req.query, req.mode)
