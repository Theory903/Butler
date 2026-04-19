"""Search service - RAG pipeline."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/search", tags=["search"])


class SearchQuery(BaseModel):
    query: str
    limit: int = 10


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str
    total: int


@router.post("/", response_model=SearchResponse)
async def search(req: SearchQuery):
    results = [
        SearchResult(title="Example Result", url="https://example.com", snippet=f"Result for: {req.query}", score=0.95),
    ]
    return SearchResponse(results=results, query=req.query, total=len(results))


@router.get("/health")
async def health():
    return {"status": "healthy"}