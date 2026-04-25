"""Routing schemas for semantic classification.

This router must never make final safety decisions.
It only produces routing signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RoutingDecision(str, Enum):
    """Embedding router output.

    Important:
    This router must never make final safety decisions.
    It only produces routing signals.
    """

    LOW_RISK_SIGNAL = "low_risk_signal"
    ESCALATE_TO_LLM = "escalate_to_llm"
    REQUIRE_POLICY_CHECK = "require_policy_check"
    REQUIRE_APPROVAL_CHECK = "require_approval_check"


@dataclass(frozen=True, slots=True)
class RoutingResult:
    decision: RoutingDecision
    confidence: float
    top_category: str | None
    reasoning: str
    similarity_scores: dict[str, float]
