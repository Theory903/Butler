"""Production semantic embedding router.

Cost-optimized semantic router that provides cheap semantic hints.
It does not make final safety, refusal, permission, or execution decisions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import structlog

from butler_core.ml.embeddings import EmbeddingProvider
from butler_core.ml.routing import RoutingDecision, RoutingResult

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SemanticCategory:
    name: str
    examples: tuple[str, ...]
    requires_llm_above: float = 0.62
    requires_policy_above: float = 0.58


DEFAULT_SEMANTIC_CATEGORIES: tuple[SemanticCategory, ...] = (
    SemanticCategory(
        name="capability.external_message.send",
        examples=(
            "The user wants to send a message to another person.",
            "The user wants to reply to an email or chat on their behalf.",
            "The action communicates externally outside the assistant.",
        ),
    ),
    SemanticCategory(
        name="capability.filesystem.mutate",
        examples=(
            "The user wants to create, edit, move, or delete files.",
            "The action changes stored project files or local documents.",
            "The request modifies filesystem state.",
        ),
    ),
    SemanticCategory(
        name="capability.credentials.access",
        examples=(
            "The action needs access to passwords, tokens, secrets, or API keys.",
            "The request requires authentication credentials.",
            "The task involves private account access.",
        ),
    ),
    SemanticCategory(
        name="risk.external_side_effect",
        examples=(
            "The action changes something in an external system.",
            "The request affects another account, person, device, service, or file.",
            "The result cannot be fully contained inside the conversation.",
        ),
    ),
    SemanticCategory(
        name="risk.physical_or_device_control",
        examples=(
            "The action controls a physical device, sensor, machine, camera, lock, or appliance.",
            "The request may affect the real physical environment.",
            "The user wants to operate hardware or IoT devices.",
        ),
    ),
    SemanticCategory(
        name="safe.answer_only",
        examples=(
            "The user only wants an explanation, summary, rewrite, or advice.",
            "The assistant can answer without using external tools.",
            "The request does not modify anything outside the chat.",
        ),
        requires_llm_above=0.85,
        requires_policy_above=0.95,
    ),
)


class SemanticEmbeddingRouter:
    """Cost-optimized semantic router.

    This router provides cheap semantic hints. It does not make final safety,
    refusal, permission, or execution decisions.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        categories: tuple[SemanticCategory, ...] = DEFAULT_SEMANTIC_CATEGORIES,
        low_risk_confidence_threshold: float = 0.72,
        ambiguity_margin: float = 0.04,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._categories = categories
        self._low_risk_confidence_threshold = low_risk_confidence_threshold
        self._ambiguity_margin = ambiguity_margin
        self._category_embeddings: dict[str, list[list[float]]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        all_examples: list[str] = []
        category_ranges: dict[str, tuple[int, int]] = {}
        cursor = 0

        for category in self._categories:
            start = cursor
            all_examples.extend(category.examples)
            cursor += len(category.examples)
            category_ranges[category.name] = (start, cursor)

        embeddings = await self._embedding_provider.embed_many(all_examples)

        for category_name, (start, end) in category_ranges.items():
            self._category_embeddings[category_name] = embeddings[start:end]

        self._initialized = True
        logger.info(
            "semantic_router_initialized",
            category_count=len(self._categories),
            exemplar_count=len(all_examples),
        )

    async def route(self, text: str) -> RoutingResult:
        await self.initialize()

        normalized_text = text.strip()
        if not normalized_text:
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                top_category=None,
                reasoning="Empty input cannot be semantically routed.",
                similarity_scores={},
            )

        query_embedding = await self._embedding_provider.embed_one(normalized_text)
        scores = self._score_categories(query_embedding)

        if not scores:
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=0.0,
                top_category=None,
                reasoning="No semantic category scores were available.",
                similarity_scores={},
            )

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_category, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second_score

        if margin < self._ambiguity_margin:
            return RoutingResult(
                decision=RoutingDecision.ESCALATE_TO_LLM,
                confidence=top_score,
                top_category=top_category,
                reasoning="Semantic routing is ambiguous; escalate to LLM classifier.",
                similarity_scores=scores,
            )

        if top_category.startswith("safe.") and top_score >= self._low_risk_confidence_threshold:
            return RoutingResult(
                decision=RoutingDecision.LOW_RISK_SIGNAL,
                confidence=top_score,
                top_category=top_category,
                reasoning="High confidence answer-only semantic signal.",
                similarity_scores=scores,
            )

        if top_category.startswith("risk.") or top_category.startswith("capability."):
            return RoutingResult(
                decision=RoutingDecision.REQUIRE_POLICY_CHECK,
                confidence=top_score,
                top_category=top_category,
                reasoning="Potential capability or side-effect signal requires policy evaluation.",
                similarity_scores=scores,
            )

        return RoutingResult(
            decision=RoutingDecision.ESCALATE_TO_LLM,
            confidence=top_score,
            top_category=top_category,
            reasoning="No safe low-risk route established; escalate to LLM classifier.",
            similarity_scores=scores,
        )

    def _score_categories(self, query_embedding: list[float]) -> dict[str, float]:
        scores: dict[str, float] = {}

        for category_name, exemplar_embeddings in self._category_embeddings.items():
            exemplar_scores = [
                self._cosine_similarity(query_embedding, exemplar_embedding)
                for exemplar_embedding in exemplar_embeddings
            ]

            if not exemplar_scores:
                continue

            top_scores = sorted(exemplar_scores, reverse=True)[:2]
            scores[category_name] = sum(top_scores) / len(top_scores)

        return scores

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0

        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0

        for left_value, right_value in zip(left, right, strict=True):
            dot += left_value * right_value
            left_norm += left_value * left_value
            right_norm += right_value * right_value

        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0

        return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
