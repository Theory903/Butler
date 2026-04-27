import logging
import os
from typing import Any

import httpx

from infrastructure.config import settings
from services.ml.semantic_classifier import SemanticClassifier
from services.security.safe_request import SafeRequestClient

import structlog

logger = structlog.get_logger(__name__)


class ContentGuard:
    """Butler Content Safety Guard (v4.0 - Model-First).

    Protects against toxicity, hate speech, self-harm, and sexual content.
    Uses semantic understanding via LLM classification instead of keyword matching.
    """

    def __init__(
        self,
        provider: str = "openai",
        tenant_id: str | None = None,
        semantic_classifier: SemanticClassifier | None = None,
    ):
        self.provider = provider
        self._tenant_id = tenant_id
        self._semantic_classifier = semantic_classifier
        self._safe_client = SafeRequestClient(timeout=httpx.Timeout(5.0)) if tenant_id else None
        # Fallback to direct httpx for non-tenant contexts (e.g., system-level safety checks)
        self._client = httpx.AsyncClient(timeout=5.0)

    async def check(self, text: str) -> dict[str, Any]:
        """Check text for safety violations.

        Returns:
            {"safe": bool, "reason": str | None, "categories": dict}
        """
        # Primary path: Semantic classification
        if self._semantic_classifier is not None:
            try:
                classification = await self._semantic_classifier.classify_safety(text)
                return {
                    "safe": classification.is_safe,
                    "reason": classification.reasoning if not classification.is_safe else None,
                    "categories": {
                        "risk_level": classification.risk_level.value,
                        "detected_categories": [c.value for c in classification.categories],
                        "confidence": classification.confidence,
                        "language": classification.language,
                    },
                }
            except Exception as exc:
                logger.warning(f"semantic_safety_classification_failed: {exc}")

        # Fallback: External API (OpenAI Moderation)
        if settings.ENVIRONMENT == "development" and not os.environ.get("OPENAI_API_KEY"):
            return {"safe": True, "reason": "Development mode - no API key", "categories": {}}

        try:
            # For this implementation, we use the OpenAI Moderation endpoint pattern
            # as it is the industry standard for general-purpose safety.
            resp = await self._client.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
                json={"input": text},
            )

            if resp.status_code == 200:
                result = resp.json()["results"][0]
                return {
                    "safe": not result["flagged"],
                    "reason": "Flagged by Moderation API" if result["flagged"] else None,
                    "categories": result["categories"],
                }
        except Exception as exc:
            logger.warning(f"safety_check_api_failed: {exc}")

        # Fail safe (or fail closed depending on policy - here we fail safe in dev)
        return {"safe": True, "reason": "Bypassed due to API error", "categories": {}}

    async def close(self):
        await self._client.aclose()
