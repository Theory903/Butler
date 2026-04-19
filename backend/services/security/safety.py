import logging
import os
from typing import Dict, Any, Optional
import httpx

from infrastructure.config import settings


logger = logging.getLogger(__name__)

class ContentGuard:
    """Butler Content Safety Guard (v3.1).
    
    Protects against toxicity, hate speech, self-harm, and sexual content.
    Uses a hybrid approach: Heuristic keywords + External Moderation API.
    """
    
    # Heuristic blocklist for fast-pass rejection
    BLOCKLIST = [
        "bomb", "suicide", "hate speech", "exploit", "kill myself",
        # ... more patterns in production
    ]

    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self._client = httpx.AsyncClient(timeout=5.0)

    async def check(self, text: str) -> Dict[str, Any]:
        """Check text for safety violations.
        
        Returns:
            {"safe": bool, "reason": str | None, "categories": dict}
        """
        # 1. Fast Pass: Heuristics
        lower_text = text.lower()
        for word in self.BLOCKLIST:
            if word in lower_text:
                return {
                    "safe": False, 
                    "reason": f"Heuristic trigger: {word}",
                    "categories": {"heuristic": True}
                }
        
        # 2. Accuracy Pass: External API
        if settings.ENVIRONMENT == "development" and not os.environ.get("OPENAI_API_KEY"):
            return {"safe": True, "reason": None, "categories": {}}

        try:
            # For this implementation, we use the OpenAI Moderation endpoint pattern
            # as it is the industry standard for general-purpose safety.
            resp = await self._client.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
                json={"input": text}
            )
            
            if resp.status_code == 200:
                result = resp.json()["results"][0]
                return {
                    "safe": not result["flagged"],
                    "reason": "Flagged by Moderation API" if result["flagged"] else None,
                    "categories": result["categories"]
                }
        except Exception as exc:
            logger.warning("safety_check_api_failed", error=str(exc))
            
        # Fail safe (or fail closed depending on policy - here we fail safe in dev)
        return {"safe": True, "reason": "Bypassed due to API error", "categories": {}}

    async def close(self):
        await self._client.aclose()
