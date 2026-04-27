"""Multilingual Embedding Router — Cost-Optimized Semantic Routing.

Uses multilingual sentence-transformers for fast, cheap semantic similarity
and routing decisions before escalating to full LLM classification.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class RoutingDecision(StrEnum):
    """Routing decision outcomes."""

    PROCEED = "proceed"
    ESCALATE_TO_LLM = "escalate_to_llm"
    REQUIRE_APPROVAL = "require_approval"
    REFUSE = "refuse"


@dataclass
class RoutingResult:
    """Result of embedding-based routing."""

    decision: RoutingDecision
    confidence: float
    reasoning: str
    language: str
    similarity_scores: dict[str, float]


class EmbeddingRouter:
    """Multilingual embedding router for cost-optimized semantic classification.

    Design principles:
    - Uses multilingual sentence-transformers for fast semantic similarity
    - Provides routing signals, not final authority for high-risk decisions
    - Escalates to LLM classifier when confidence is low or risk is high
    - Supports cross-lingual semantic matching
    """

    # Recommended multilingual models
    RECOMMENDED_MODELS = [
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "intfloat/multilingual-e5-small",
        "intfloat/multilingual-e5-base",
        "BAAI/bge-m3",
    ]

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        confidence_threshold: float = 0.7,
        risk_threshold: float = 0.6,
    ) -> None:
        """Initialize the embedding router.

        Args:
            model_name: Name of the multilingual sentence-transformer model
            confidence_threshold: Minimum confidence to proceed without escalation
            risk_threshold: Risk threshold for requiring approval
        """
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._risk_threshold = risk_threshold
        self._model: SentenceTransformer | None = None
        self._load_lock = asyncio.Lock()

        # Pre-computed embeddings for reference categories
        self._reference_embeddings: dict[str, list[float]] = {}
        self._reference_categories: dict[str, str] = {
            # Safety categories
            "toxicity": "toxic harmful offensive language",
            "hate_speech": "hate discrimination prejudice racism",
            "self_harm": "suicide self-harm depression hurt myself",
            "sexual_content": "sexual explicit inappropriate content",
            "violence": "violence threat harm danger",
            "pii": "personal private information sensitive data",
            # Risk categories
            "critical": "critical dangerous destructive delete financial money",
            "device": "device iot hardware physical control",
            "write": "write modify create update change",
            "read": "read search query retrieve fetch",
            "builtin": "math calculate format echo simple",
        }

    async def initialize(self) -> None:
        """Lazy-load the embedding model and compute reference embeddings."""
        async with self._load_lock:
            if self._model is not None:
                return

            try:
                logger.info("loading_embedding_model", model=self._model_name)
                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(
                    None, lambda: SentenceTransformer(self._model_name)
                )

                # Pre-compute reference embeddings
                self._compute_reference_embeddings()
                logger.info("embedding_model_loaded", model=self._model_name)
            except Exception as exc:
                logger.error("embedding_model_load_failed", error=str(exc))
                raise

    def _compute_reference_embeddings(self) -> None:
        """Compute embeddings for reference categories."""
        if self._model is None:
            return

        for category, description in self._reference_categories.items():
            embedding = self._model.encode(description)
            self._reference_embeddings[category] = embedding.tolist()

    async def route_safety(self, text: str) -> RoutingResult:
        """Route safety classification using embedding similarity.

        Args:
            text: Input text to route

        Returns:
            RoutingResult with decision and confidence
        """
        await self.initialize()

        if self._model is None:
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                reasoning="Embedding model unavailable",
                language="unknown",
                similarity_scores={},
            )

        try:
            # Compute embedding for input text
            loop = asyncio.get_event_loop()
            text_embedding = await loop.run_in_executor(None, lambda: self._model.encode(text))

            # Compute similarity with safety categories
            safety_categories = [
                "toxicity",
                "hate_speech",
                "self_harm",
                "sexual_content",
                "violence",
                "pii",
            ]
            similarity_scores = {}

            for category in safety_categories:
                if category in self._reference_embeddings:
                    ref_embedding = self._reference_embeddings[category]
                    similarity = self._cosine_similarity(text_embedding, ref_embedding)
                    similarity_scores[category] = similarity

            # Find highest similarity
            max_similarity = max(similarity_scores.values()) if similarity_scores else 0.0
            max_category = (
                max(similarity_scores.items(), key=lambda x: x[1])[0]
                if similarity_scores
                else "none"
            )

            # Make routing decision
            if max_similarity > self._risk_threshold:
                return RoutingResult(
                    decision=RoutingDecision.REFUSE,
                    confidence=max_similarity,
                    reasoning=f"High similarity to {max_category} category",
                    language="detected",  # Would need actual language detection
                    similarity_scores=similarity_scores,
                )
            if max_similarity > self._confidence_threshold:
                return RoutingResult(
                    decision=RoutingDecision.ESCALATE_TO_LLM,
                    confidence=max_similarity,
                    reasoning=f"Moderate similarity to {max_category} - escalate for verification",
                    language="detected",
                    similarity_scores=similarity_scores,
                )
            return RoutingResult(
                decision=RoutingDecision.PROCEED,
                confidence=max_similarity,
                reasoning="Low similarity to safety categories",
                language="detected",
                similarity_scores=similarity_scores,
            )
        except Exception as exc:
            logger.warning("embedding_safety_routing_failed", error=str(exc))
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                reasoning="Embedding routing failed - escalate to LLM",
                language="unknown",
                similarity_scores={},
            )

    async def route_risk(self, tool_name: str, description: str | None = None) -> RoutingResult:
        """Route risk classification using embedding similarity.

        Args:
            tool_name: Name of the tool
            description: Optional description of the tool

        Returns:
            RoutingResult with decision and confidence
        """
        await self.initialize()

        if self._model is None:
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                reasoning="Embedding model unavailable",
                language="unknown",
                similarity_scores={},
            )

        try:
            # Combine tool name and description for better semantic matching
            combined_text = f"{tool_name} {description or ''}"

            # Compute embedding
            loop = asyncio.get_event_loop()
            text_embedding = await loop.run_in_executor(
                None, lambda: self._model.encode(combined_text)
            )

            # Compute similarity with risk categories
            risk_categories = ["critical", "device", "write", "read", "builtin"]
            similarity_scores = {}

            for category in risk_categories:
                if category in self._reference_embeddings:
                    ref_embedding = self._reference_embeddings[category]
                    similarity = self._cosine_similarity(text_embedding, ref_embedding)
                    similarity_scores[category] = similarity

            # Find highest similarity
            max_similarity = max(similarity_scores.values()) if similarity_scores else 0.0
            max_category = (
                max(similarity_scores.items(), key=lambda x: x[1])[0]
                if similarity_scores
                else "builtin"
            )

            # Make routing decision
            if max_category == "critical" and max_similarity > self._confidence_threshold:
                return RoutingResult(
                    decision=RoutingDecision.REQUIRE_APPROVAL,
                    confidence=max_similarity,
                    reasoning="High similarity to critical operations",
                    language="detected",
                    similarity_scores=similarity_scores,
                )
            if max_category == "device" and max_similarity > self._confidence_threshold:
                return RoutingResult(
                    decision=RoutingDecision.REQUIRE_APPROVAL,
                    confidence=max_similarity,
                    reasoning="High similarity to device/physical operations",
                    language="detected",
                    similarity_scores=similarity_scores,
                )
            if max_similarity > self._confidence_threshold:
                return RoutingResult(
                    decision=RoutingDecision.PROCEED,
                    confidence=max_similarity,
                    reasoning=f"High confidence classification as {max_category}",
                    language="detected",
                    similarity_scores=similarity_scores,
                )
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=max_similarity,
                reasoning="Low confidence - escalate to LLM for verification",
                language="detected",
                similarity_scores=similarity_scores,
            )
        except Exception as exc:
            logger.warning("embedding_risk_routing_failed", error=str(exc))
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                reasoning="Embedding routing failed - escalate to LLM",
                language="unknown",
                similarity_scores={},
            )

    def _cosine_similarity(self, vec1: list[float] | Any, vec2: list[float] | Any) -> float:
        """Compute cosine similarity between two vectors."""
        import numpy as np

        a = np.array(vec1)
        b = np.array(vec2)
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)
