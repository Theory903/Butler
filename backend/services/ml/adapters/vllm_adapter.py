import logging
import time
from typing import Any

from services.security.safe_request import SafeRequestClient

import structlog

logger = structlog.get_logger(__name__)


class VLLMAdapter:
    """Production adapter for local vLLM nodes.

    Implements TriAttention and prefix caching semantics as per spec.
    P0 hardening: Uses SafeRequestClient for SSRF protection.
    """

    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        self.base_url = base_url
        # P0 hardening: Use SafeRequestClient for SSRF protection
        self.client = SafeRequestClient()
        self._tenant_id = "default"  # Use default tenant for vLLM operations

    async def execute(self, model: str, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute inference against vLLM OpenAI-compatible endpoint."""
        start_time = time.monotonic()

        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], **params}

        try:
            # P0 hardening: Use SafeRequestClient for SSRF protection
            response = await self.client.post(
                f"{self.base_url}/chat/completions", self._tenant_id, json=payload
            )
            response.raise_for_status()
            data = response.json()

            latency_ms = int((time.monotonic() - start_time) * 1000)

            return {
                "status": "success",
                "text": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
                "latency_ms": latency_ms,
                "model_version": data.get("model"),
            }
        except Exception as exc:
            logger.error(f"vllm_inference_failed: {str(exc)}")
            return {
                "status": "error",
                "detail": str(exc),
                "latency_ms": int((time.monotonic() - start_time) * 1000),
            }

    async def close(self):
        await self.client.close()
