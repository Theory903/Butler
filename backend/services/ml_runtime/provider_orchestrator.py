"""Provider orchestrator that integrates all orchestration components."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator

from .openclaw_layer.provider_registry import (
    ProviderRegistry,
    ProviderSpec,
    create_default_registry,
)
from .openclaw_layer.credential_pool import (
    CredentialPool,
    Credential,
    create_credential,
)
from .openclaw_layer.failover_engine import (
    FailoverEngine,
    RetryPolicy,
)
from .openclaw_layer.rate_limiter import (
    MultiProviderRateLimiter,
    RateLimiter,
)
from .openclaw_layer.observability import (
    ProviderObservability,
    log_provider_request,
    log_provider_response,
)
from .openclaw_layer.cost_tracker import CostTracker
from .openclaw_layer.config import (
    ProviderOrchestratorConfig,
    load_config_from_env,
)
from .langchain_adapter import (
    LangChainProviderAdapter,
    LangChainAdapterConfig,
)


@dataclass
class MLRequest:
    """Request to the ML runtime."""
    provider: str
    prompt: str
    model: Optional[str] = None
    system_message: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MLResponse:
    """Response from the ML runtime."""
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProviderOrchestrator:
    """Main orchestrator for ML runtime provider operations.
    
    This class integrates all orchestration components:
    - Provider registry with normalization
    - Credential pool with load balancing
    - Failover engine with exponential backoff
    - Rate limiter with burst allowance
    - LangChain adapter for unified provider abstraction
    - Observability (logging, metrics, tracing)
    - Cost tracking
    """
    
    def __init__(
        self,
        provider_registry: Optional[ProviderRegistry] = None,
        credential_pool: Optional[CredentialPool] = None,
        failover_engine: Optional[FailoverEngine] = None,
        rate_limiter: Optional[MultiProviderRateLimiter] = None,
        langchain_adapter: Optional[LangChainProviderAdapter] = None,
        observability: Optional[ProviderObservability] = None,
        cost_tracker: Optional[CostTracker] = None,
        config: Optional[ProviderOrchestratorConfig] = None,
        langchain_config: Optional[LangChainAdapterConfig] = None,
    ):
        self.config = config or load_config_from_env()
        self.langchain_config = langchain_config or LangChainAdapterConfig()
        
        # Initialize components
        self.provider_registry = provider_registry or create_default_registry()
        self.credential_pool = credential_pool or CredentialPool()
        self.failover_engine = failover_engine or FailoverEngine(
            retry_policy=RetryPolicy(
                max_retries=self.config.retry.max_retries,
                initial_delay_seconds=self.config.retry.initial_delay_seconds,
                backoff_factor=self.config.retry.backoff_factor,
                max_delay_seconds=self.config.retry.max_delay_seconds,
                jitter=self.config.retry.jitter,
            )
        )
        self.rate_limiter = rate_limiter or MultiProviderRateLimiter()
        self.observability = observability or ProviderObservability(
            enabled=self.config.enable_observability
        )
        self.cost_tracker = cost_tracker or CostTracker(
            enabled=self.config.enable_cost_tracking
        )
        
        # Initialize LangChain adapter
        self.langchain_adapter = LangChainProviderAdapter(
            provider_registry=self.provider_registry,
            credential_pool=self.credential_pool,
            observability=self.observability,
            cost_tracker=self.cost_tracker,
            config=self.langchain_config,
        )
    
    async def execute_request(self, request: MLRequest) -> MLResponse:
        """Execute an ML request with full orchestration.
        
        This method:
        1. Checks rate limits
        2. Gets a credential from the pool
        3. Executes with retry and failover logic
        4. Tracks observability and cost
        5. Returns the response
        """
        start_time = asyncio.get_event_loop().time()
        
        # Check rate limits
        if not self.rate_limiter.can_request(request.provider):
            wait_time = self.rate_limiter.get_wait_time(request.provider)
            raise RuntimeError(
                f"Rate limit exceeded for provider {request.provider}. "
                f"Wait {wait_time:.2f}s before retrying."
            )
        
        # Execute with failover
        async def _execute():
            result = await self.langchain_adapter.execute_generate_text(
                provider_name=request.provider,
                prompt=request.prompt,
                model=request.model,
                system_message=request.system_message,
                tools=request.tools,
            )
            return result
        
        try:
            text = await self.failover_engine.execute_with_retry(
                _execute,
                provider=request.provider,
            )
        except Exception as e:
            # Try failover to another provider
            available_providers = [
                spec.name for spec in self.provider_registry.list_providers()
            ]
            alternative_provider = self.failover_engine.switch_provider(
                request.provider,
                available_providers,
            )
            
            if alternative_provider:
                request.provider = alternative_provider
                text = await self.failover_engine.execute_with_retry(
                    _execute,
                    provider=alternative_provider,
                )
            else:
                raise
        
        # Record rate limit
        self.rate_limiter.record_request(request.provider)
        
        # Calculate duration
        duration_seconds = asyncio.get_event_loop().time() - start_time
        
        # Build response
        response = MLResponse(
            text=text,
            provider=request.provider,
            model=request.model or "default",
            duration_seconds=duration_seconds,
            metadata=request.metadata,
        )
        
        return response
    
    async def execute_stream(self, request: MLRequest) -> AsyncIterator[str]:
        """Execute a streaming ML request with full orchestration."""
        # Check rate limits
        if not self.rate_limiter.can_request(request.provider):
            wait_time = self.rate_limiter.get_wait_time(request.provider)
            raise RuntimeError(
                f"Rate limit exceeded for provider {request.provider}. "
                f"Wait {wait_time:.2f}s before retrying."
            )
        
        try:
            # Execute with streaming directly (failover for streaming is complex, simplify for now)
            async for chunk in self.langchain_adapter.execute_stream_text(
                provider_name=request.provider,
                prompt=request.prompt,
                model=request.model,
                system_message=request.system_message,
            ):
                yield chunk
        except Exception as e:
            # Try failover to another provider
            available_providers = [
                spec.name for spec in self.provider_registry.list_providers()
            ]
            alternative_provider = self.failover_engine.switch_provider(
                request.provider,
                available_providers,
            )
            
            if alternative_provider:
                request.provider = alternative_provider
                async for chunk in self.langchain_adapter.execute_stream_text(
                    provider_name=alternative_provider,
                    prompt=request.prompt,
                    model=request.model,
                    system_message=request.system_message,
                ):
                    yield chunk
            else:
                raise
        
        # Record rate limit
        self.rate_limiter.record_request(request.provider)
    
    def add_credential(
        self,
        provider: str,
        key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a credential to the orchestrator's credential pool."""
        self.credential_pool.add_credential(
            create_credential(provider, key, metadata or {})
        )
    
    def add_tenant_credential(
        self,
        tenant_id: str,
        provider: str,
        key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a tenant-specific credential to the credential pool.
        
        This allows different tenants to use different API keys for the same provider.
        The credential is tagged with the tenant_id for isolation.
        """
        credential_metadata = metadata or {}
        credential_metadata["tenant_id"] = tenant_id
        
        self.credential_pool.add_credential(
            create_credential(provider, key, credential_metadata)
        )
    
    async def execute_request_with_tenant(
        self,
        request: MLRequest,
        tenant_id: str,
        tenant_api_key: str | None = None,
    ) -> MLResponse:
        """Execute an ML request with tenant-specific credentials.
        
        Args:
            request: The ML request to execute
            tenant_id: The tenant ID for credential isolation
            tenant_api_key: Optional tenant-specific API key to use instead of default credentials
        
        Returns:
            MLResponse with the generated content and metadata
        """
        # If tenant provides a custom API key, use it
        if tenant_api_key:
            # Temporarily add the tenant's credential
            self.add_tenant_credential(tenant_id, request.provider, tenant_api_key)
            
            try:
                return await self.execute_request(request)
            finally:
                # Clean up tenant credential after execution
                # In production, you might want to keep it cached for performance
                pass
        else:
            # Use default credentials
            return await self.execute_request(request)
    
    def get_provider_health(self, provider: str) -> Dict[str, Any]:
        """Get health status for a provider."""
        circuit_breaker_health = self.failover_engine.get_provider_health(provider)
        pool_stats = self.credential_pool.get_pool_stats(provider)
        rate_limit_stats = self.rate_limiter.get_stats(provider)
        
        return {
            "circuit_breaker": circuit_breaker_health,
            "credential_pool": {
                "total": pool_stats.total_credentials,
                "healthy": pool_stats.healthy_credentials,
                "degraded": pool_stats.degraded_credentials,
                "unhealthy": pool_stats.unhealthy_credentials,
                "rate_limited": pool_stats.rate_limited_credentials,
            },
            "rate_limiter": rate_limit_stats,
        }
    
    def get_all_provider_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status for all providers."""
        providers = [spec.name for spec in self.provider_registry.list_providers()]
        return {
            provider: self.get_provider_health(provider)
            for provider in providers
        }
    
    def get_cost_summary(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Get cost summary for a provider or all providers."""
        if provider:
            summary = self.cost_tracker.get_provider_cost(provider)
            return {
                "provider": provider,
                "total_requests": summary.total_requests,
                "total_cost_usd": summary.total_cost_usd,
                "avg_cost_per_request": summary.avg_cost_per_request,
            }
        else:
            summaries = self.cost_tracker.get_all_provider_costs()
            return {
                provider: {
                    "total_requests": summary.total_requests,
                    "total_cost_usd": summary.total_cost_usd,
                    "avg_cost_per_request": summary.avg_cost_per_request,
                }
                for provider, summary in summaries.items()
            }
    
    def get_metrics(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Get metrics for a provider or all providers."""
        if provider:
            metrics = self.observability.get_provider_metrics(provider)
            return {
                "provider": provider,
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "failed_requests": metrics.failed_requests,
                "success_rate": metrics.success_rate,
                "avg_duration_seconds": metrics.avg_duration_seconds,
            }
        else:
            metrics = self.observability.get_all_metrics()
            return {
                provider: {
                    "total_requests": summary.total_requests,
                    "successful_requests": summary.successful_requests,
                    "failed_requests": summary.failed_requests,
                    "success_rate": summary.success_rate,
                    "avg_duration_seconds": summary.avg_duration_seconds,
                }
                for provider, summary in metrics.items()
            }


def create_provider_orchestrator(
    config: Optional[ProviderOrchestratorConfig] = None,
    langchain_config: Optional[LangChainAdapterConfig] = None,
) -> ProviderOrchestrator:
    """Create a provider orchestrator with default components."""
    return ProviderOrchestrator(
        config=config,
        langchain_config=langchain_config,
    )
