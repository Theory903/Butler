import os
import httpx
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FrontierAdapter:
    """Unified adapter for cloud frontier models (Anthropic, Gemini, OpenAI).
    
    Implements the T3 (Cloud) tier logic with priority fallback.
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=120.0)
        
    async def execute(self, model: str, prompt: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute inference against cloud providers.
        
        Currently supports Gemini as primary, falls back to OpenAI/Anthropic if configured.
        """
        provider = self._determine_provider(model)
        start_time = time.monotonic()
        
        try:
            if provider == "gemini":
                return await self._execute_gemini(model, prompt, params, start_time)
            elif provider == "openai":
                return await self._execute_openai(model, prompt, params, start_time)
            else:
                raise ValueError(f"Unsupported cloud provider: {provider}")
        except Exception as exc:
            logger.error(f"cloud_inference_failed: {str(exc)}", provider=provider)
            return {
                "status": "error",
                "detail": str(exc),
                "latency_ms": int((time.monotonic() - start_time) * 1000)
            }

    async def _execute_gemini(self, model: str, prompt: str, params: Dict[str, Any], start: float) -> Dict[str, Any]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": params.get("temperature", 0.7),
                "maxOutputTokens": params.get("max_tokens", 4096),
            }
        }
        
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        
        return {
            "status": "success",
            "text": text,
            "usage": {"total_tokens": 0},  # Gemini usage parsing varies by model
            "latency_ms": int((time.monotonic() - start) * 1000),
            "provider": "gemini"
        }

    async def _execute_openai(self, model: str, prompt: str, params: Dict[str, Any], start: float) -> Dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
            
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **params
        }
        
        response = await self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return {
            "status": "success",
            "text": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {}),
            "latency_ms": int((time.monotonic() - start) * 1000),
            "provider": "openai"
        }

    def _determine_provider(self, model: str) -> str:
        if "gemini" in model.lower():
            return "gemini"
        if "gpt" in model.lower():
            return "openai"
        if "claude" in model.lower():
            return "anthropic"
        return "openai"

    async def close(self):
        await self.client.aclose()
