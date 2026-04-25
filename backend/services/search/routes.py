from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.deps import get_search_service
from domain.search.contracts import ISearchService

router = APIRouter(prefix="/search", tags=["search"])


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=20)
    mode: str = Field(default="auto", min_length=1, max_length=64)


class SearchResultDTO(BaseModel):
    title: str
    url: str
    snippet: str
    score: float
    published_date: str | None = None
    extraction_method: str | None = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    total: int
    latency_ms: float
    citations: list[dict[str, Any]]
    results: list[SearchResultDTO]


class HealthResponse(BaseModel):
    status: str
    service: str
    provider_available: bool


@router.post("/", response_model=SearchResponse)
async def search(
    req: SearchQuery,
    search_service: ISearchService = Depends(get_search_service),
) -> SearchResponse:
    """Search endpoint.

    Transport only:
    - validate request
    - delegate to injected search service
    - map result to response DTO
    """
    try:
        evidence_pack = await search_service.search(
            query=req.query,
            mode=req.mode,
            max_results=req.limit,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search service failed: {exc}",
        ) from exc

    results = [
        SearchResultDTO(
            title=item.title,
            url=item.url,
            snippet=item.content or "",
            score=item.score,
            published_date=(
                item.freshness.isoformat() if getattr(item, "freshness", None) else None
            ),
            extraction_method=getattr(item, "extraction_method", None),
        )
        for item in evidence_pack.results
    ]

    return SearchResponse(
        query=evidence_pack.query,
        mode=evidence_pack.mode,
        total=evidence_pack.result_count,
        latency_ms=evidence_pack.latency_ms,
        citations=evidence_pack.citations,
        results=results,
    )


@router.get("/health", response_model=HealthResponse)
async def health(
    search_service: ISearchService = Depends(get_search_service),
) -> HealthResponse:
    """Readiness-style health for the search service.

    This is intentionally lightweight. A deeper readiness path can probe
    provider upstreams separately if Butler exposes that later.
    """
    provider_available = True

    # Optional best-effort probe if the concrete service exposes one later.
    health_check = getattr(search_service, "health_check", None)
    if callable(health_check):
        try:
            provider_available = bool(await health_check())
        except Exception:
            provider_available = False

    return HealthResponse(
        status="healthy" if provider_available else "degraded",
        service="search",
        provider_available=provider_available,
    )
