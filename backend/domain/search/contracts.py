from __future__ import annotations
from abc import abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from domain.base import DomainService

class SearchClassification(BaseModel):
    # Core skip/search-type flags
    skipSearch: bool = Field(False, description="Skip the search step (greetings, trivially short).")
    personalSearch: bool = Field(False, description="Query is about the user's own data.")
    transactionalSearch: bool = Field(False, description="User wants to perform an action (buy, book, schedule).")
    researchSearch: bool = Field(False, description="Academic or research query (paper, arxiv, study).")
    discussionSearch: bool = Field(False, description="Community/forum-oriented query.")
    ambiguousSearch: bool = Field(False, description="Intent unclear — no bucket fired, not trivially skip.")
    # Orthogonal widget flags (not exclusive with search type)
    showWeatherWidget: bool = Field(False, description="Query involves weather/temperature/forecast.")
    showStockWidget: bool = Field(False, description="Query involves stocks, crypto, or market data.")
    showCalculationWidget: bool = Field(False, description="Query involves a calculation or unit conversion.")
    # Retained for backward compatibility — superseded by researchSearch
    academicSearch: bool = Field(False, description="[Deprecated: use researchSearch] Academic search.")


class ClassifierResult(BaseModel):
    classification: SearchClassification
    standaloneFollowUp: str

class SearchResult(BaseModel):
    url: str
    title: str
    content: str
    snippet: str
    engine: str
    score: float = 0.0
    published_date: Optional[str] = None

class AnsweringEngineResult(BaseModel):
    answer: str
    sources: List[SearchResult]
    classification: SearchClassification
    widgets: List[Dict[str, Any]] = []

class ISearchService(DomainService):
    @abstractmethod
    async def search(self, query: str, **kwargs) -> List[SearchResult]:
        pass

    @abstractmethod
    async def answer(self, query: str, chat_history: List[Dict[str, str]] = []) -> AnsweringEngineResult:
        pass


class ISearchAdapter(DomainService):
    """Abstraction over the concrete search adapter (SearxNGAdapter, etc.).

    AnsweringEngine depends on this contract, not on SearxNGAdapter directly,
    so any adapter (SearXNG, Brave, Bing, mock) can be injected without
    changing the engine.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        categories: List[str] | None = None,
        language: str = "en",
        num_results: int = 10,
    ) -> List[Dict]:
        """Run a web search and return raw result dicts."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the adapter's upstream is reachable."""
