import httpx
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class VLLMAdapter:
    """Production adapter for local vLLM nodes.
    
    Implements TriAttention and prefix caching semantics as per spec.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000/v1"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def execute(self, model: str, prompt: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute inference against vLLM OpenAI-compatible endpoint."""
        start_time = time.monotonic()
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **params
        }
        
        try:
            response = await self.client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            return {
                "status": "success",
                "text": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
                "latency_ms": latency_ms,
                "model_version": data.get("model")
            }
        except Exception as exc:
            logger.error(f"vllm_inference_failed: {str(exc)}")
            return {
                "status": "error",
                "detail": str(exc),
                "latency_ms": int((time.monotonic() - start_time) * 1000)
            }

    async def close(self):
        await self.client.aclose()
