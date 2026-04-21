import asyncio
import structlog
from typing import Dict, Any, Optional

from domain.ml.contracts import ReasoningRequest
from services.ml.registry import ModelRegistry, ModelProviderFactory
from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from core.observability import ButlerMetrics, get_metrics

logger = structlog.get_logger(__name__)

class MLRuntimeManager:
    """
    Manages the ML Inference Runtime Profiles (v3.0).
    Uses the ModelProviderFactory to execute reasoning requests.
    """

    def __init__(
        self, 
        registry: Optional[ModelRegistry] = None,
        breakers: Optional[CircuitBreakerRegistry] = None,
        health_agent: Any | None = None,
        metrics: ButlerMetrics | None = None,
        max_concurrency: int = 20,
    ):
        self._registry = registry or ModelRegistry()
        self._breakers = breakers
        self._health = health_agent
        self._metrics = metrics or get_metrics()
        self._semaphore = asyncio.Semaphore(max_concurrency)

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

        # 2. Prepare candidates for Tier 3 resilience
        candidates = [entry]
        if entry.tier == 3:
            fallbacks = self._registry.get_fallback_profiles(tier=3, exclude_name=profile_name)
            candidates.extend(fallbacks)

        last_error = None
        for candidate in candidates:
            try:
                # 3. Get provider via factory
                provider = ModelProviderFactory.get_provider(candidate.provider)
                
                # 4. Create ReasoningRequest
                request = ReasoningRequest(
                    prompt=payload.get("prompt", ""),
                    system_prompt=payload.get("system_prompt"),
                    temperature=payload.get("params", {}).get("temperature", 0.7),
                    max_tokens=payload.get("params", {}).get("max_tokens", 4096),
                    metadata={
                        "model": candidate.version,
                        "triattention": candidate.tri_attention,
                        **payload.get("metadata", {})
                    }
                )

                logger.info("inference_attempt", profile=candidate.name, provider=candidate.provider)
                
                async with self._semaphore:
                    response = await provider.generate(request)
                
                    return {
                        "status": "success",
                        "content": response.content,
                        "usage": response.usage,
                        "model_version": response.model_version,
                        "provider": candidate.provider
                    }
            except Exception as exc:
                logger.warning("inference_attempt_failed", profile=candidate.name, error=str(exc))
                last_error = exc
                # Continue loop to next candidate
                continue

        # 5. Exhausted all candidates
        logger.error("inference_exhausted", profile=profile_name, error=str(last_error))
        return {
            "status": "error",
            "detail": f"All fallback providers exhausted. Last error: {str(last_error)}"
        }

    async def on_startup(self):
        """Initialize ML runtime on application startup."""
        logger.info("ml_runtime_starting")
        # Warm up providers by pre-loading model configs
        for name in self._registry.MODELS:
            entry = self._registry.MODELS[name]
            logger.debug("ml_profile_available", profile=name, provider=entry.provider)
        logger.info("ml_runtime_started", profile_count=len(self._registry.MODELS))

    async def shutdown(self):
        logger.info("ml_runtime_shutting_down")
