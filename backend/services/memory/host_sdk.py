"""Memory Host SDK — Python port of openclaw `packages/memory-host-sdk/`.

Provides plugin-side memory primitives:
- Memory query DSL (QMD-like) parser
- Embedding model limits and batch utilities
- Memory schema validation
- Plugin memory isolation contracts
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class MemoryStatus(str, Enum):
    """Lifecycle status for a memory operation (mirrors openclaw `status.ts`)."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Embedding model limits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingModelLimits:
    """Hard limits for an embedding model (port of `embedding-model-limits.ts`)."""

    max_input_tokens: int
    max_batch_size: int
    dimensions: int

    def fits(self, token_count: int, batch_size: int = 1) -> bool:
        return token_count <= self.max_input_tokens and batch_size <= self.max_batch_size


DEFAULT_LIMITS: dict[str, EmbeddingModelLimits] = {
    "text-embedding-3-small": EmbeddingModelLimits(8191, 2048, 1536),
    "text-embedding-3-large": EmbeddingModelLimits(8191, 2048, 3072),
    "text-embedding-ada-002": EmbeddingModelLimits(8191, 2048, 1536),
    "embed-english-v3.0": EmbeddingModelLimits(512, 96, 1024),
    "nomic-embed-text": EmbeddingModelLimits(8192, 256, 768),
    "BAAI/bge-large-en-v1.5": EmbeddingModelLimits(512, 256, 1024),
}


# ---------------------------------------------------------------------------
# Batch utils + errors
# ---------------------------------------------------------------------------


@dataclass
class BatchError:
    """Error from a batch operation (port of `batch-error-utils.ts`)."""

    index: int
    message: str
    retryable: bool = False
    code: str | None = None


def chunk_batch(items: list[Any], batch_size: int) -> list[list[Any]]:
    """Split `items` into chunks of `batch_size`."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def filter_retryable(errors: list[BatchError]) -> list[BatchError]:
    """Return only retryable errors (port of `batch-error-utils.ts`)."""
    return [e for e in errors if e.retryable]


# ---------------------------------------------------------------------------
# Memory schema
# ---------------------------------------------------------------------------


@dataclass
class MemorySchema:
    """Memory record schema (port of `memory-schema.ts`)."""

    id: str
    content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tier: str = "hot"
    status: MemoryStatus = MemoryStatus.PENDING

    def validate(self) -> bool:
        if not self.id or not self.content:
            return False
        if self.embedding is not None and not all(isinstance(x, (int, float)) for x in self.embedding):
            return False
        return True


# ---------------------------------------------------------------------------
# QMD query parser (Query Memory DSL)
# ---------------------------------------------------------------------------


@dataclass
class QMDQuery:
    """Parsed QMD query (port of `qmd-query-parser.ts`)."""

    text: str
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 10
    tier: str | None = None


_QMD_FILTER_RE = re.compile(r"(\w+):\s*([\w\-_/.]+|\"[^\"]+\")")
_QMD_LIMIT_RE = re.compile(r"\blimit:\s*(\d+)", re.IGNORECASE)
_QMD_TIER_RE = re.compile(r"\btier:\s*(hot|warm|cold|archive)\b", re.IGNORECASE)


def parse_qmd_query(raw: str) -> QMDQuery:
    """Parse a QMD-style query string.

    Examples:
        "hello world tier:hot limit:5"
        "user:alice topic:billing"
    """
    if not raw or not raw.strip():
        return QMDQuery(text="")

    filters: dict[str, Any] = {}
    limit = 10
    tier: str | None = None

    limit_match = _QMD_LIMIT_RE.search(raw)
    if limit_match:
        limit = int(limit_match.group(1))
        raw = raw.replace(limit_match.group(0), "")

    tier_match = _QMD_TIER_RE.search(raw)
    if tier_match:
        tier = tier_match.group(1).lower()
        raw = raw.replace(tier_match.group(0), "")

    for key, value in _QMD_FILTER_RE.findall(raw):
        if key.lower() in {"limit", "tier"}:
            continue
        filters[key] = value.strip('"')
        raw = raw.replace(f"{key}:{value}", "")

    return QMDQuery(text=raw.strip(), filters=filters, limit=limit, tier=tier)


# ---------------------------------------------------------------------------
# QMD process pipeline
# ---------------------------------------------------------------------------


@dataclass
class QMDProcessResult:
    """Result of a QMD process pipeline run (port of `qmd-process.ts`)."""

    query: QMDQuery
    candidates: list[MemorySchema]
    status: MemoryStatus = MemoryStatus.READY
    errors: list[BatchError] = field(default_factory=list)


class QMDProcessor:
    """Pipeline that turns a raw query into ranked memory candidates.

    Plugin authors compose this with their own memory backend.
    """

    def __init__(self, limits: EmbeddingModelLimits | None = None):
        self._limits = limits

    async def process(
        self,
        raw_query: str,
        retriever: Any,
    ) -> QMDProcessResult:
        """Process a raw query through retrieval.

        Args:
            raw_query: User-supplied query string.
            retriever: Object with `async retrieve(query: QMDQuery) -> list[MemorySchema]`.
        """
        query = parse_qmd_query(raw_query)

        if self._limits and len(query.text) > self._limits.max_input_tokens * 4:
            return QMDProcessResult(
                query=query,
                candidates=[],
                status=MemoryStatus.FAILED,
                errors=[BatchError(index=0, message="query exceeds embedding token limit")],
            )

        try:
            candidates = await retriever.retrieve(query)
            return QMDProcessResult(query=query, candidates=candidates)
        except Exception as e:
            logger.error(f"qmd_process_failed: {e}")
            return QMDProcessResult(
                query=query,
                candidates=[],
                status=MemoryStatus.FAILED,
                errors=[BatchError(index=0, message=str(e), retryable=True)],
            )


# ---------------------------------------------------------------------------
# Backend config
# ---------------------------------------------------------------------------


@dataclass
class MemoryBackendConfig:
    """Memory backend connection config (port of `backend-config.ts`)."""

    backend_type: str  # "redis" | "postgres" | "qdrant" | "neo4j"
    connection_string: str
    namespace: str = "default"
    timeout_seconds: int = 30
    extra: dict[str, Any] = field(default_factory=dict)
