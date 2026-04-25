from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.base import DomainService


def _to_camel(field_name: str) -> str:
    parts = field_name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ButlerSearchBaseModel(BaseModel):
    """Shared strict base model for Butler search contracts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=_to_camel,
    )


class SearchClassification(ButlerSearchBaseModel):
    """Structured search-intent classification.

    These flags are intentionally orthogonal. Multiple buckets may be true
    at the same time.
    """

    skip_search: bool = Field(
        default=False,
        description="Skip the search step for greetings or trivially short requests.",
    )
    personal_search: bool = Field(
        default=False,
        description="Query is about the user's own data or prior context.",
    )
    transactional_search: bool = Field(
        default=False,
        description="User wants to perform an action such as buying, booking, or scheduling.",
    )
    research_search: bool = Field(
        default=False,
        description="Academic, research, or literature-heavy query.",
    )
    discussion_search: bool = Field(
        default=False,
        description="Community, forum, or discussion-oriented query.",
    )
    ambiguous_search: bool = Field(
        default=False,
        description="Intent remains unclear and no strong category fired.",
    )

    show_weather_widget: bool = Field(
        default=False,
        description="Query involves weather, temperature, or forecast.",
    )
    show_stock_widget: bool = Field(
        default=False,
        description="Query involves stocks, crypto, or market data.",
    )
    show_calculation_widget: bool = Field(
        default=False,
        description="Query involves calculation or unit conversion.",
    )

    academic_search: bool = Field(
        default=False,
        description="Backward-compatible alias of research-style search.",
    )

    @model_validator(mode="after")
    def synchronize_backward_compat_flags(self) -> SearchClassification:
        # Keep backward compatibility without allowing drift.
        if self.research_search and not self.academic_search:
            self.academic_search = True
        elif self.academic_search and not self.research_search:
            self.research_search = True
        return self


class ClassifierResult(ButlerSearchBaseModel):
    """Search classifier output."""

    classification: SearchClassification
    standalone_follow_up: str = Field(
        default="",
        description="Standalone rewritten follow-up query if the user asked a contextual follow-up.",
    )

    @field_validator("standalone_follow_up")
    @classmethod
    def validate_standalone_follow_up(cls, value: str) -> str:
        return value.strip()


class SearchResult(ButlerSearchBaseModel):
    """Normalized search result item."""

    url: str
    title: str
    content: str = ""
    snippet: str = ""
    engine: str
    score: float = 0.0
    published_date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url", "title", "engine")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized

    @field_validator("content", "snippet")
    @classmethod
    def normalize_optional_text(cls, value: str) -> str:
        return value.strip()


class SearchEvidencePack(ButlerSearchBaseModel):
    """Normalized search package returned by the search service."""

    query: str
    mode: str = "auto"
    results: list[SearchResult] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    result_count: int = 0
    latency_ms: float = 0.0
    provider: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query", "mode")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized

    @field_validator("provider")
    @classmethod
    def validate_optional_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SearchWidget(ButlerSearchBaseModel):
    """Optional UI/widget hint returned by the answering/search layer."""

    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Widget kind must not be empty")
        return normalized


class AnsweringEngineResult(ButlerSearchBaseModel):
    """Final answering-engine response."""

    answer: str
    sources: list[SearchResult] = Field(default_factory=list)
    classification: SearchClassification
    widgets: list[SearchWidget] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Answer must not be empty")
        return normalized


class ISearchService(DomainService):
    """Contract for Butler search orchestration."""

    @abstractmethod
    async def search(
        self,
        query: str,
        **kwargs: Any,
    ) -> SearchEvidencePack:
        """Run search and return a normalized evidence package."""
        raise NotImplementedError

    @abstractmethod
    async def answer(
        self,
        query: str,
        chat_history: Sequence[dict[str, str]] | None = None,
    ) -> AnsweringEngineResult:
        """Answer a query using search + reasoning."""
        raise NotImplementedError


class ISearchAdapter(DomainService):
    """Contract for raw upstream search adapters.

    Answering/search engines should depend on this contract, not on a
    specific provider implementation.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        categories: list[str] | None = None,
        language: str | None = None,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Run a web search and return raw upstream result dicts."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the adapter's upstream is reachable."""
        raise NotImplementedError
