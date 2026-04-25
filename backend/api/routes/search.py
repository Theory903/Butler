from typing import Any, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.routes.gateway import get_current_account
from domain.auth.contracts import AccountContext


# Dependency injection for routing
async def get_search_service() -> Any:
    from services.search.extraction import ContentExtractor
    from services.search.service import SearchService

    extractor = ContentExtractor()
    return cast(Any, SearchService(extractor))


router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    mode: str = "auto"


@router.post("/")
async def search(
    req: SearchRequest,
    account: AccountContext = Depends(get_current_account),
    svc: Any = Depends(get_search_service),
):
    # Depending on architecture, we might just return the Pydantic dict representation of EvidencePack
    # Since EvidencePack is a dataclass, we can return it safely with FastAPI
    return await svc.search(req.query, req.mode)
