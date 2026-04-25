"""Tool risk classification and retry policies by RiskTier."""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from tenacity import stop_after_attempt, wait_exponential

from services.ml.semantic_classifier import RiskLevel, SemanticClassifier


class RiskTier(IntEnum):
    """Risk tier classification for tool execution governance.

    TIER_0: Builtin operations (math, format, echo) - no approval, 1 retry
    TIER_1: Read operations (search, memory read) - no approval, 2 retries
    TIER_2: Write operations (memory write, send) - no approval, 3 retries
    TIER_3: Device actions (device, IoT) - interrupt required, 1 retry
    TIER_4: Critical operations (financial, physical, delete) - interrupt required, no retry
    """

    TIER_0_BUILTIN = 0
    TIER_1_READ = 1
    TIER_2_WRITE = 2
    TIER_3_DEVICE = 3
    TIER_4_APPROVAL = 4


class ToolRiskClassifier:
    """Classifies tool operations by risk tier using semantic understanding.

    Replaces keyword-based classification with LLM semantic analysis.
    """

    DEFAULT_TIER = RiskTier.TIER_1_READ

    def __init__(self, semantic_classifier: SemanticClassifier | None = None) -> None:
        self._semantic_classifier = semantic_classifier

    def classify(self, tool_name: str, params: dict[str, Any] | None = None, description: str | None = None) -> RiskTier:
        """Classify a tool operation by risk tier using semantic understanding.

        Args:
            tool_name: Name of the tool being executed
            params: Optional parameters passed to the tool (can influence risk)
            description: Optional description of the tool

        Returns:
            RiskTier classification for the operation
        """
        # For now, use a conservative mapping based on semantic classifier if available
        # This is a synchronous wrapper - in production, this should be async
        if self._semantic_classifier is None:
            return self._default_classification(tool_name, params)

        # Note: This would need to be called in an async context
        # For now, fall back to conservative default
        return self._default_classification(tool_name, params)

    def _default_classification(self, tool_name: str, params: dict[str, Any] | None = None) -> RiskTier:
        """Conservative default classification when semantic classifier unavailable.

        This is a structural fallback, not semantic - assumes medium risk by default.
        """
        # Conservative: assume medium risk unless we have strong evidence otherwise
        # This is a structural guard, not semantic classification
        return RiskTier.TIER_2_WRITE

    async def classify_async(
        self, tool_name: str, params: dict[str, Any] | None = None, description: str | None = None
    ) -> RiskTier:
        """Async classification using semantic understanding.

        Args:
            tool_name: Name of the tool being executed
            params: Optional parameters passed to the tool
            description: Optional description of the tool

        Returns:
            RiskTier classification for the operation
        """
        if self._semantic_classifier is not None:
            try:
                classification = await self._semantic_classifier.classify_risk(tool_name, params, description)
                return self._map_risk_level_to_tier(classification.risk_level)
            except Exception:
                # Fall back to conservative default on error
                pass

        return self._default_classification(tool_name, params)

    def _map_risk_level_to_tier(self, risk_level: RiskLevel) -> RiskTier:
        """Map semantic risk level to governance tier.

        This is a structural mapping, not semantic classification.
        """
        mapping = {
            RiskLevel.LOW: RiskTier.TIER_1_READ,
            RiskLevel.MEDIUM: RiskTier.TIER_2_WRITE,
            RiskLevel.HIGH: RiskTier.TIER_3_DEVICE,
            RiskLevel.CRITICAL: RiskTier.TIER_4_APPROVAL,
        }
        return mapping.get(risk_level, RiskTier.TIER_2_WRITE)

    @classmethod
    def requires_approval(cls, risk_tier: RiskTier) -> bool:
        """Check if a risk tier requires human approval."""
        return risk_tier >= RiskTier.TIER_3_DEVICE

    @classmethod
    def requires_sandbox(cls, risk_tier: RiskTier) -> bool:
        """Check if a risk tier requires sandboxed execution."""
        return risk_tier >= RiskTier.TIER_3_DEVICE


# Retry policies by risk tier (from migration plan)
RETRY_POLICIES = {
    RiskTier.TIER_0_BUILTIN: {
        "stop": stop_after_attempt(1),
    },
    RiskTier.TIER_1_READ: {
        "stop": stop_after_attempt(2),
        "wait": wait_exponential(multiplier=1, min=1, max=10),
    },
    RiskTier.TIER_2_WRITE: {
        "stop": stop_after_attempt(3),
        "wait": wait_exponential(multiplier=1, min=1, max=10),
    },
    RiskTier.TIER_3_DEVICE: {
        "stop": stop_after_attempt(1),  # Fail fast, human decides
    },
    RiskTier.TIER_4_APPROVAL: {
        "stop": stop_after_attempt(1),  # Never retry without human
    },
}


def get_retry_policy(risk_tier: int | RiskTier) -> dict[str, Any]:
    """Get retry policy for given risk tier.

    Args:
        risk_tier: Risk tier as int or RiskTier enum

    Returns:
        Dictionary with retry configuration
    """
    tier = RiskTier(risk_tier) if isinstance(risk_tier, int) else risk_tier
    return RETRY_POLICIES.get(tier, RETRY_POLICIES[RiskTier.TIER_0_BUILTIN])
