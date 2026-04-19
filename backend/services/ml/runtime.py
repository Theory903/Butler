import structlog
from typing import Dict, Any, Optional

from domain.ml.contracts import ReasoningRequest
from services.ml.registry import ModelRegistry, ModelProviderFactory

logger = structlog.get_logger(__name__)

class MLRuntimeManager:
    """
    Manages the ML Inference Runtime Profiles (v3.0).
    Uses the ModelProviderFactory to execute reasoning requests.
    """

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self._registry = registry or ModelRegistry()

    def get_profile(self, name: str) -> Optional[Any]:
        """Return the model entry/configuration for a given profile name."""
        return self._registry.MODELS.get(name)

    async def execute_inference(self, profile_name: str, payload: dict) -> dict:
        """
        Execute an inference request against a ReasoningProvider.
        """
        # 1. Resolve model entry from registry
        entry = self._registry.get_active_model(profile_name)
        if not entry:
            raise ValueError(f"Unknown or inactive model profile: {profile_name}")
            
        # 2. Get provider via factory
        provider = ModelProviderFactory.get_provider(entry.provider)
        
        # 3. Create ReasoningRequest
        request = ReasoningRequest(
            prompt=payload.get("prompt", ""),
            system_prompt=payload.get("system_prompt"),
            temperature=payload.get("params", {}).get("temperature", 0.7),
            max_tokens=payload.get("params", {}).get("max_tokens", 4096),
            metadata={
                "model": entry.version,
                "triattention": entry.tri_attention,
                **payload.get("metadata", {})
            }
        )

        logger.info("inference_started", profile=profile_name, provider=entry.provider)
        
        try:
            response = await provider.generate(request)
            
            return {
                "status": "success",
                "content": response.content,
                "usage": response.usage,
                "model_version": response.model_version,
                "provider": entry.provider
            }
        except Exception as exc:
            logger.error("inference_failed", profile=profile_name, error=str(exc))
            return {
                "status": "error",
                "detail": str(exc)
            }

    async def shutdown(self):
        # Providers use shared httpx clients; individual shutdown logic if needed
        pass
