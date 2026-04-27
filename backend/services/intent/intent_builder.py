"""Intent Builder Service - Pre-retrieval layer for Butler.

Normalizes user input and extracts intent context before tool retrieval.
This layer improves retrieval quality by removing noise, extracting intent,
and attaching constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IntentConstraints:
    """Constraints extracted from intent for tool retrieval."""

    risk_level: str = "L2"  # Default safe level
    latency: Literal["low", "medium", "high"] = "medium"
    cost_sensitive: bool = False
    max_tools: int = 12


@dataclass(frozen=True, slots=True)
class IntentContext:
    """Normalized intent context for tool retrieval."""

    query: str
    intent_type: Literal["action", "info", "transactional"]
    constraints: IntentConstraints
    session_context: dict[str, Any] | None = None
    original_input: str = ""


class IntentBuilder:
    """Intent builder for normalizing user input and extracting intent context.

    This is a pre-retrieval layer that shapes the query before ToolScope runs.
    """

    def __init__(
        self,
        enabled: bool = True,
        default_risk_level: str = "L2",
        max_query_length: int = 500,
    ):
        """Initialize intent builder.

        Args:
            enabled: Whether intent building is enabled.
            default_risk_level: Default risk level for constraints.
            max_query_length: Maximum length for normalized query.
        """
        self._enabled = enabled
        self._default_risk_level = default_risk_level
        self._max_query_length = max_query_length

    def build(
        self,
        user_input: str,
        session_context: dict[str, Any] | None = None,
        account_permissions: frozenset[str] | None = None,
    ) -> IntentContext:
        """Build intent context from raw user input.

        Args:
            user_input: Raw user input string.
            session_context: Optional session context from MemoryService.
            account_permissions: Optional account permissions for constraint inference.

        Returns:
            IntentContext with normalized query and extracted intent.
        """
        if not self._enabled:
            # Pass through if disabled
            return IntentContext(
                query=self._truncate(user_input),
                intent_type="info",
                constraints=IntentConstraints(risk_level=self._default_risk_level),
                session_context=session_context,
                original_input=user_input,
            )

        # Normalize query
        normalized_query = self._normalize_query(user_input)

        # Extract intent type
        intent_type = self._classify_intent(normalized_query, session_context)

        # Extract constraints
        constraints = self._extract_constraints(
            normalized_query, intent_type, account_permissions, session_context
        )

        logger.info(
            "intent_context_built",
            original_input=user_input[:100],
            normalized_query=normalized_query[:100],
            intent_type=intent_type,
            risk_level=constraints.risk_level,
        )

        return IntentContext(
            query=normalized_query,
            intent_type=intent_type,
            constraints=constraints,
            session_context=session_context,
            original_input=user_input,
        )

    def _normalize_query(self, query: str) -> str:
        """Normalize query by removing noise and standardizing format.

        Args:
            query: Raw query string.

        Returns:
            Normalized query string.
        """
        if not query:
            return ""

        # Strip whitespace
        normalized = query.strip()

        # Remove excessive whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Remove common filler phrases
        fillers = [
            r"^(please|can you|could you|i would like|i want|i need)\s+",
            r"\s+(please|thanks|thank you)$",
        ]
        for pattern in fillers:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

        # Truncate to max length
        normalized = self._truncate(normalized)

        return normalized

    def _classify_intent(
        self, query: str, session_context: dict[str, Any] | None
    ) -> Literal["action", "info", "transactional"]:
        """Classify the intent type from query and context.

        Args:
            query: Normalized query string.
            session_context: Optional session context.

        Returns:
            Intent type classification.
        """
        query_lower = query.lower()

        # Transactional intent indicators
        transactional_patterns = [
            r"\b(buy|purchase|pay|transfer|send money|order|book|reserve)\b",
            r"\b(delete|remove|cancel|unsubscribe)\b",
            r"\b(create|add|insert|register|sign up)\b",
        ]

        # Action intent indicators
        action_patterns = [
            r"\b(send|email|message|call|notify|alert)\b",
            r"\b(search|find|lookup|get|retrieve|fetch)\b",
            r"\b(update|modify|change|edit)\b",
            r"\b(execute|run|start|stop|launch)\b",
        ]

        # Check for transactional intent
        for pattern in transactional_patterns:
            if re.search(pattern, query_lower):
                return "transactional"

        # Check for action intent
        for pattern in action_patterns:
            if re.search(pattern, query_lower):
                return "action"

        # Default to info intent
        return "info"

    def _extract_constraints(
        self,
        query: str,
        intent_type: str,
        account_permissions: frozenset[str] | None,
        session_context: dict[str, Any] | None,
    ) -> IntentConstraints:
        """Extract constraints from query and context.

        Args:
            query: Normalized query string.
            intent_type: Classified intent type.
            account_permissions: Account permissions.
            session_context: Session context.

        Returns:
            Extracted constraints.
        """
        # Default constraints
        constraints = IntentConstraints(risk_level=self._default_risk_level)

        # Adjust risk level based on intent type
        if intent_type == "transactional":
            constraints = IntentConstraints(risk_level="L2", max_tools=8)
        elif intent_type == "action":
            constraints = IntentConstraints(risk_level="L1", max_tools=10)

        # Adjust based on permissions
        if account_permissions:
            # If has admin permissions, allow higher risk
            if "admin" in account_permissions:
                constraints = IntentConstraints(
                    risk_level="L3", max_tools=constraints.max_tools
                )

        # Check for latency sensitivity in query
        query_lower = query.lower()
        if any(word in query_lower for word in ["quick", "fast", "asap", "urgent"]):
            constraints = IntentConstraints(
                risk_level=constraints.risk_level,
                latency="low",
                max_tools=constraints.max_tools,
            )

        # Check for cost sensitivity
        if any(word in query_lower for word in ["cheap", "free", "low cost", "budget"]):
            constraints = IntentConstraints(
                risk_level=constraints.risk_level,
                cost_sensitive=True,
                max_tools=constraints.max_tools,
            )

        return constraints

    def _truncate(self, text: str) -> str:
        """Truncate text to max length.

        Args:
            text: Text to truncate.

        Returns:
            Truncated text.
        """
        if len(text) <= self._max_query_length:
            return text
        return text[: self._max_query_length].rstrip()
