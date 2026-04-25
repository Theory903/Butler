from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from time import monotonic
from typing import Any

import structlog

from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from core.observability import ButlerMetrics, get_metrics
from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningTier,
)
from domain.orchestration.router import OperationRouter
from services.ml.provider_health import MLProviderHealthTracker
from services.ml.registry import ModelProviderFactory, ModelRegistry

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeCandidate:
    """Resolved runtime execution candidate."""

    name: str
    provider_name: str
    model_version: str
    tier: ReasoningTier
    tri_attention: bool = False


class MLRuntimeManager(IReasoningRuntime):
    """Typed Butler ML runtime manager.

    Responsibilities:
    - resolve model candidates from registry
    - apply bounded concurrency
    - integrate circuit breakers
    - execute provider calls through a typed reasoning contract
    - apply fallback candidates when allowed
    - expose a stable runtime surface to the rest of Butler
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        breakers: CircuitBreakerRegistry | None = None,
        health_tracker: MLProviderHealthTracker | None = None,
        metrics: ButlerMetrics | None = None,
        max_concurrency: int = 20,
        operation_router: OperationRouter | None = None,
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than 0")

        self._registry = registry or ModelRegistry()
        self._breakers = breakers
        self._health = health_tracker or MLProviderHealthTracker()
        self._metrics = metrics or get_metrics()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._operation_router = operation_router

    async def generate(
        self,
        request: ReasoningRequest,
        tenant_id: str,  # Required for multi-tenant isolation
        *,
        preferred_tier: ReasoningTier | None = None,
    ) -> ReasoningResponse:
        """Generate a full reasoning response.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        # Check ML inference operation admission through router
        if self._operation_router:
            from domain.orchestration.router import AdmissionDecision, OperationRequest, OperationType

            operation_request = OperationRequest(
                operation_type=OperationType.CHAT,  # ML inference uses CHAT type
                tenant_id=tenant_id,
                account_id=tenant_id,  # ReasoningRequest may not have account_id
                user_id=None,
                tool_name=None,
                risk_tier=None,
                estimated_cost=None,
            )

            _, admission = self._operation_router.route(operation_request)
            if admission.decision != AdmissionDecision.ALLOW:
                logger.warning(
                    "ml_inference_denied_by_router",
                    extra={
                        "tenant_id": tenant_id,
                        "reason": admission.reason,
                    },
                )
                return ReasoningResponse(
                    content="ML inference denied by operation router",
                    raw_response=None,
                    usage={},
                    finish_reason="denied",
                )

        candidates = self._resolve_candidates(request, preferred_tier=preferred_tier)
        last_error: Exception | None = None

        for candidate in candidates:
            started_at = monotonic()
            try:
                response = await self._execute_candidate(
                    candidate=candidate,
                    request=request,
                )
                duration_ms = int((monotonic() - started_at) * 1000)

                self._record_success(
                    candidate=candidate,
                    duration_ms=duration_ms,
                )

                enriched_usage = dict(response.usage or {})
                enriched_usage.setdefault("duration_ms", duration_ms)

                return ReasoningResponse(
                    content=response.content,
                    raw_response=response.raw_response,
                    usage=enriched_usage,
                    model_version=response.model_version or candidate.model_version,
                    provider_name=response.provider_name or candidate.provider_name,
                    finish_reason=response.finish_reason,
                    metadata={
                        **dict(response.metadata or {}),
                        "runtime_candidate": candidate.name,
                        "runtime_tier": candidate.tier.value,
                    },
                )
            except Exception as exc:
                duration_ms = int((monotonic() - started_at) * 1000)
                last_error = exc
                self._record_failure(
                    candidate=candidate,
                    duration_ms=duration_ms,
                    exc=exc,
                )
                logger.warning(
                    "ml_runtime_candidate_failed",
                    candidate=candidate.name,
                    provider=candidate.provider_name,
                    tier=candidate.tier.value,
                    error=str(exc),
                )
                continue

        logger.error(
            "ml_runtime_exhausted",
            preferred_tier=preferred_tier.value if preferred_tier else None,
            error=str(last_error) if last_error else None,
        )
        raise RuntimeError(
            f"All runtime candidates failed. Last error: {last_error}"
        ) from last_error

    async def generate_stream(
        self,
        request: ReasoningRequest,
        tenant_id: str,  # Required for multi-tenant isolation
        *,
        preferred_tier: ReasoningTier | None = None,
    ) -> AsyncGenerator[str]:
        """Stream a reasoning response as text chunks.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        candidates = self._resolve_candidates(request, preferred_tier=preferred_tier)
        last_error: Exception | None = None

        for candidate in candidates:
            started_at = monotonic()
            try:
                provider = self._get_provider(candidate.provider_name)
                breaker = self._get_breaker(candidate.name)
                enriched_request = self._enrich_request(request, candidate)

                async with self._semaphore:
                    if breaker is not None:
                        with breaker:
                            async for chunk in provider.generate_stream(enriched_request):
                                yield chunk
                    else:
                        async for chunk in provider.generate_stream(enriched_request):
                            yield chunk

                duration_ms = int((monotonic() - started_at) * 1000)
                self._record_success(candidate=candidate, duration_ms=duration_ms)
                return
            except Exception as exc:
                duration_ms = int((monotonic() - started_at) * 1000)
                last_error = exc
                self._record_failure(
                    candidate=candidate,
                    duration_ms=duration_ms,
                    exc=exc,
                )
                logger.warning(
                    "ml_runtime_stream_candidate_failed",
                    candidate=candidate.name,
                    provider=candidate.provider_name,
                    tier=candidate.tier.value,
                    error=str(exc),
                )
                continue

        logger.error(
            "ml_runtime_stream_exhausted",
            preferred_tier=preferred_tier.value if preferred_tier else None,
            error=str(last_error) if last_error else None,
        )
        raise RuntimeError(
            f"All streaming runtime candidates failed. Last error: {last_error}"
        ) from last_error

    async def on_startup(self) -> None:
        """Initialize runtime visibility and warm metadata."""
        model_entries = self._registry.list_entries()
        logger.info("ml_runtime_starting", profile_count=len(model_entries))

        for entry in model_entries:
            logger.debug(
                "ml_profile_available",
                profile=entry.get("name"),
                provider=entry.get("provider"),
                tier=entry.get("tier"),
            )

        logger.info("ml_runtime_started", profile_count=len(model_entries))

    async def shutdown(self) -> None:
        logger.info("ml_runtime_shutting_down")

    def get_profile(self, name: str) -> Any | None:
        """Return raw registry profile for compatibility with legacy callers."""
        return self._registry.MODELS.get(name)

    async def execute_inference(
        self,
        profile_name: str,
        payload: dict[str, Any],
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> dict[str, Any]:
        """Legacy compatibility adapter.

        Keep this temporarily while older services migrate to generate()/generate_stream().

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        params = payload.get("params", {})
        if not isinstance(params, dict):
            params = {}

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        try:
            temperature = float(params.get("temperature", 0.0))
        except (TypeError, ValueError):
            temperature = 0.0

        try:
            max_tokens = int(params.get("max_tokens", 4096))
        except (TypeError, ValueError):
            max_tokens = 4096

        request = ReasoningRequest(
            prompt=str(payload.get("prompt", "") or "").strip() or " ",
            system_prompt=payload.get("system_prompt"),
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=dict(metadata),
        )

        try:
            response = await self.generate(request, tenant_id=tenant_id)
            return {
                "status": "success",
                "content": response.content,
                "usage": response.usage,
                "model_version": response.model_version,
                "provider": response.provider_name,
                "metadata": response.metadata,
            }
        except Exception as exc:
            logger.error("legacy_execute_inference_failed", profile=profile_name, error=str(exc))
            return {
                "status": "error",
                "detail": str(exc),
            }

    async def to_langchain_model(
        self,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-6-20250529",
    ) -> ButlerChatModel:  # noqa: F821 — forward reference resolved at runtime
        """Create LangChain-compatible model for agentic workflows."""
        from langchain.models import ButlerChatModel, ChatModelFactory  # noqa: F401

        return ChatModelFactory.create(
            runtime_manager=self,
            tenant_id="default",
            preferred_model=model,
        )

    def _resolve_candidates(
        self,
        request: ReasoningRequest,
        *,
        preferred_tier: ReasoningTier | None,
    ) -> list[RuntimeCandidate]:
        """Resolve ordered execution candidates from request hints and registry with health gating."""
        preferred_model = request.preferred_model or self._metadata_model_hint(request)

        # If no preferred model in request, use settings.DEFAULT_MODEL
        if not preferred_model:
            from infrastructure.config import settings
            if settings.DEFAULT_MODEL:
                preferred_model = settings.DEFAULT_MODEL

        if preferred_model:
            entry = self._registry.get_active_model(preferred_model)
            if entry is None:
                raise ValueError(f"Unknown or inactive model profile: {preferred_model}")

            candidates = [self._entry_to_candidate(entry)]

            if entry.tier == ReasoningTier.T3:
                fallbacks = self._registry.get_fallback_profiles(
                    tier=ReasoningTier.T3,
                    exclude_name=entry.name,
                )
                candidates.extend(self._entry_to_candidate(item) for item in fallbacks)

            return self._filter_by_health(candidates)

        resolved_tier = preferred_tier or request.preferred_tier or ReasoningTier.T2
        registry_tier = self._contract_tier_to_registry_tier(resolved_tier)

        primary_entry = self._select_primary_entry_for_tier(resolved_tier)
        if primary_entry is None:
            raise RuntimeError(f"No active model entries found for tier {resolved_tier.value}")

        candidates = [self._entry_to_candidate(primary_entry)]

        for item in self._registry.get_fallback_profiles(
            tier=resolved_tier,
            exclude_name=primary_entry.name,
        ):
            candidates.append(self._entry_to_candidate(item))

        return self._filter_by_health(candidates)

    def _select_primary_entry_for_tier(self, tier: ReasoningTier) -> Any | None:
        """Select the primary active model entry for a reasoning tier."""
        entries = self._registry.get_active_by_tier(tier)
        if not entries:
            return None

        entries = sorted(entries, key=lambda item: item.cost_per_1k_tokens)
        return entries[0]

    def _entry_to_candidate(self, entry: Any) -> RuntimeCandidate:
        return RuntimeCandidate(
            name=str(entry.name),
            provider_name=str(entry.provider),
            model_version=str(entry.version),
            tier=entry.tier,
            tri_attention=bool(getattr(entry, "tri_attention", False)),
        )

    def _dedupe_candidates(self, candidates: list[RuntimeCandidate]) -> list[RuntimeCandidate]:
        seen: set[str] = set()
        result: list[RuntimeCandidate] = []

        for candidate in candidates:
            if candidate.name in seen:
                continue
            seen.add(candidate.name)
            result.append(candidate)

        return result

    def _filter_by_health(self, candidates: list[RuntimeCandidate]) -> list[RuntimeCandidate]:
        """Filter candidates based on health status, removing unhealthy providers."""
        from domain.ml.runtime_health import HealthStatus

        filtered = []
        for candidate in candidates:
            if self._health is None:
                # No health tracker - include all candidates
                filtered.append(candidate)
                continue

            provider_health = self._health.get_provider_health(candidate.provider_name)
            
            # Skip unhealthy providers
            if provider_health.status == HealthStatus.UNHEALTHY:
                logger.warning(
                    "ml_runtime_skip_unhealthy_provider",
                    provider=candidate.provider_name,
                    status=provider_health.status.value,
                    error_rate=provider_health.error_rate,
                )
                continue

            # Include healthy and degraded providers
            filtered.append(candidate)

        if not filtered:
            logger.warning(
                "ml_runtime_all_candidates_unhealthy",
                total_candidates=len(candidates),
            )

        return filtered

    def _enrich_request(
        self,
        request: ReasoningRequest,
        candidate: RuntimeCandidate,
    ) -> ReasoningRequest:
        """Attach runtime-resolved metadata to the outgoing request."""
        metadata = dict(request.metadata)
        metadata.update(
            {
                "model": candidate.model_version,
                "runtime_candidate": candidate.name,
                "runtime_provider": candidate.provider_name,
                "runtime_tier": candidate.tier.value,
                "triattention": candidate.tri_attention,
            }
        )

        return ReasoningRequest.model_validate(
            {
                **request.model_dump(),
                "metadata": metadata,
                "preferred_tier": candidate.tier,
            },
            strict=False,
        )

    async def _execute_candidate(
        self,
        *,
        candidate: RuntimeCandidate,
        request: ReasoningRequest,
    ) -> ReasoningResponse:
        provider = self._get_provider(candidate.provider_name)
        breaker = self._get_breaker(candidate.name)
        enriched_request = self._enrich_request(request, candidate)

        async with self._semaphore:
            if breaker is not None:
                with breaker:
                    return await provider.generate(enriched_request)
            return await provider.generate(enriched_request)

    def _get_provider(self, provider_name: str):
        return ModelProviderFactory.get_provider(provider_name)

    def _get_breaker(self, profile_name: str):
        if self._breakers is None:
            return None

        try:
            if hasattr(self._breakers, "get"):
                return self._breakers.get(profile_name)
            if hasattr(self._breakers, "get_breaker"):
                return self._breakers.get_breaker(profile_name)
        except Exception:
            logger.exception("ml_runtime_breaker_lookup_failed", profile=profile_name)

        return None

    def _record_success(self, *, candidate: RuntimeCandidate, duration_ms: int) -> None:
        logger.info(
            "ml_runtime_inference_succeeded",
            candidate=candidate.name,
            provider=candidate.provider_name,
            tier=candidate.tier.value,
            duration_ms=duration_ms,
        )

        if self._health is not None:
            try:
                self._health.record_model_success(
                    provider_name=candidate.provider_name,
                    latency_ms=float(duration_ms),
                )
            except Exception:
                logger.exception(
                    "ml_runtime_health_success_record_failed",
                    candidate=candidate.name,
                )

        try:
            self._metrics.increment(
                "ml_runtime_requests_total",
                tags={
                    "candidate": candidate.name,
                    "provider": candidate.provider_name,
                    "tier": candidate.tier.value,
                    "status": "success",
                },
            )
            self._metrics.observe(
                "ml_runtime_request_duration_ms",
                duration_ms,
                tags={
                    "candidate": candidate.name,
                    "provider": candidate.provider_name,
                    "tier": candidate.tier.value,
                },
            )
        except Exception:
            logger.exception(
                "ml_runtime_metrics_success_record_failed",
                candidate=candidate.name,
            )

    def _record_failure(
        self,
        *,
        candidate: RuntimeCandidate,
        duration_ms: int,
        exc: Exception,
    ) -> None:
        if isinstance(exc, CircuitOpenError):
            logger.warning(
                "ml_runtime_circuit_open",
                candidate=candidate.name,
                provider=candidate.provider_name,
            )

        if self._health is not None:
            try:
                self._health.record_model_failure(
                    provider_name=candidate.provider_name,
                    latency_ms=float(duration_ms),
                )
            except Exception:
                logger.exception(
                    "ml_runtime_health_failure_record_failed",
                    candidate=candidate.name,
                )

        try:
            self._metrics.increment(
                "ml_runtime_requests_total",
                tags={
                    "candidate": candidate.name,
                    "provider": candidate.provider_name,
                    "tier": candidate.tier.value,
                    "status": "failure",
                },
            )
            self._metrics.observe(
                "ml_runtime_request_duration_ms",
                duration_ms,
                tags={
                    "candidate": candidate.name,
                    "provider": candidate.provider_name,
                    "tier": candidate.tier.value,
                },
            )
        except Exception:
            logger.exception(
                "ml_runtime_metrics_failure_record_failed",
                candidate=candidate.name,
            )

    def _metadata_model_hint(self, request: ReasoningRequest) -> str | None:
        raw_model = request.metadata.get("model")
        if isinstance(raw_model, str) and raw_model.strip():
            return raw_model.strip()
        return None

    def _contract_tier_to_registry_tier(self, tier: ReasoningTier) -> int:
        mapping = {
            ReasoningTier.T0: 0,
            ReasoningTier.T1: 1,
            ReasoningTier.T2: 2,
            ReasoningTier.T3: 3,
        }
        return mapping[tier]

    def _registry_tier_to_contract_tier(self, tier: int) -> ReasoningTier:
        mapping = {
            0: ReasoningTier.T0,
            1: ReasoningTier.T1,
            2: ReasoningTier.T2,
            3: ReasoningTier.T3,
        }
        return mapping.get(tier, ReasoningTier.T2)
