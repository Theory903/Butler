"""ButlerSmartRouter — Phase 5.

Selects the correct ML inference tier (T0–T3) for every request,
respecting latency budgets, complexity signals from intent classification,
and the TriAttention serving profile toggle.

Tier ladder:
  T0  pattern match          0 ms    IntentClassifier._pattern_match()
  T1  keyword classifier     <1 ms   IntentClassifier._keyword_classify()
  T2  local lightweight LLM  <400 ms vLLM local (Qwen3/TriAttention)
  T3  cloud frontier model   <2 s    external_api profile (Anthropic/OpenAI/Gemini)

Routing decision is driven by:
  - intent complexity (simple → T1, complex → T2/T3)
  - requires_tools flag (always T2+ for tool calls)
  - context_size (large prompt → T3 if T2 KV budget exceeded)
  - tri_attention_enabled config toggle (profile B)
  - latency_budget_ms per request (overrides tier escalation)

Butler sovereignty rule:
  - SmartRouter never calls any LLM directly. It emits a RoutingDecision
    that the RuntimeKernel uses to select the correct backend config.
  - Hermes never sees this routing decision — it receives only the final
    model/provider designation through HermesAgentBackend.
  - SmartRouter does not mutate the Envelope or any domain model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import structlog

from domain.ml.contracts import IntentResult
from services.ml.runtime import MLRuntimeManager

logger = structlog.get_logger(__name__)


class ModelTier(IntEnum):
    T0 = 0   # Pattern match — zero cost, zero latency
    T1 = 1   # Keyword ML — sub-ms
    T2 = 2   # Local LLM (vLLM / TriAttention)
    T3 = 3   # Cloud frontier (Anthropic / OpenAI / Gemini)


# Latency budget thresholds (ms) for tier escalation
_T2_MAX_LATENCY_MS = 400
_T3_MAX_LATENCY_MS = 2000

# Prompt token size above which T2 KV budget is exceeded → escalate to T3
_T2_KV_OVERFLOW_TOKENS = 10_000


@dataclass(frozen=True)
class RoutingDecision:
    """Immutable routing decision emitted by ButlerSmartRouter.

    Consumed by RuntimeKernel to configure HermesAgentBackend.
    Never exposed to API callers.
    """
    tier: ModelTier
    runtime_profile: str           # Key into MLRuntimeManager.PROFILES
    provider: str                  # vllm | external_api | pattern | keyword
    tri_attention: bool
    latency_budget_ms: int
    estimated_prompt_tokens: int
    reason: str
    override_by_user: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class RouterRequest:
    """Input to ButlerSmartRouter.route()."""
    intent: IntentResult
    message: str
    context_token_count: int = 0
    latency_budget_ms: int = _T3_MAX_LATENCY_MS
    force_tier: ModelTier | None = None   # explicit override (admin/test)


class ButlerSmartRouter:
    """T0–T3 model tier router.

    Usage:
        router = ButlerSmartRouter(runtime=runtime_manager, tri_attention_enabled=True)
        decision = router.route(RouterRequest(intent=intent_result, message=msg))
        # Pass decision to RuntimeKernel
    """

    def __init__(
        self,
        runtime: MLRuntimeManager,
        tri_attention_enabled: bool = False,
    ) -> None:
        self._runtime = runtime
        self._tri_attention = tri_attention_enabled

    def route(self, request: RouterRequest) -> RoutingDecision:
        """Select the inference tier and runtime profile for this request."""
        start = time.monotonic_ns()

        # 1. Explicit override (admin / integration test)
        if request.force_tier is not None:
            decision = self._make_decision(
                tier=request.force_tier,
                request=request,
                reason="force_tier override",
                override=True,
            )
            self._log(decision, start)
            return decision

        # 2. T0 — high-confidence pattern match (no LLM needed)
        if (
            request.intent.confidence >= 0.9
            and request.intent.complexity == "simple"
            and not request.intent.requires_tools
            and not request.intent.requires_memory
        ):
            decision = self._make_decision(
                tier=ModelTier.T0,
                request=request,
                reason="high-confidence pattern match; no tools/memory needed",
            )
            self._log(decision, start)
            return decision

        # 3. T1 — keyword classifier with no tool requirement
        if (
            request.intent.confidence >= 0.75
            and request.intent.complexity == "simple"
            and not request.intent.requires_tools
        ):
            decision = self._make_decision(
                tier=ModelTier.T1,
                request=request,
                reason="keyword-classified simple intent; no tools",
            )
            self._log(decision, start)
            return decision

        # 4. T3 — escalate if prompt exceeds T2 KV budget or latency is tight
        if request.context_token_count > _T2_KV_OVERFLOW_TOKENS:
            decision = self._make_decision(
                tier=ModelTier.T3,
                request=request,
                reason=f"context ({request.context_token_count} tokens) exceeds T2 KV budget",
            )
            self._log(decision, start)
            return decision

        if request.latency_budget_ms <= _T2_MAX_LATENCY_MS and self._has_t2():
            # Tight budget but T2 fits
            decision = self._make_decision(
                tier=ModelTier.T2,
                request=request,
                reason="latency budget tight; T2 local LLM fits window",
            )
            self._log(decision, start)
            return decision

        # 5. Complex / tool / approval → prefer T2 local if available, else T3
        if request.intent.complexity == "complex" or request.intent.requires_tools:
            if self._has_t2():
                decision = self._make_decision(
                    tier=ModelTier.T2,
                    request=request,
                    reason="complex intent or tool requirement → T2 local LLM",
                )
            else:
                decision = self._make_decision(
                    tier=ModelTier.T3,
                    request=request,
                    reason="complex intent → T3 cloud (T2 not available)",
                )
            self._log(decision, start)
            return decision

        # 6. Default: T3 cloud frontier
        decision = self._make_decision(
            tier=ModelTier.T3,
            request=request,
            reason="default: cloud frontier for unclassified complex intent",
        )
        self._log(decision, start)
        return decision

    # ── Internals ─────────────────────────────────────────────────────────────

    def _has_t2(self) -> bool:
        """Whether a T2 local LLM profile is configured."""
        return self._runtime.get_profile("local-reasoning-qwen3") is not None

    def _make_decision(
        self,
        tier: ModelTier,
        request: RouterRequest,
        reason: str,
        override: bool = False,
    ) -> RoutingDecision:
        profile_name, provider, tri = self._profile_for_tier(tier, request)
        return RoutingDecision(
            tier=tier,
            runtime_profile=profile_name,
            provider=provider,
            tri_attention=tri,
            latency_budget_ms=request.latency_budget_ms,
            estimated_prompt_tokens=request.context_token_count + len(request.message.split()),
            reason=reason,
            override_by_user=override,
            metadata={
                "intent_label": request.intent.label,
                "intent_confidence": request.intent.confidence,
                "requires_tools": request.intent.requires_tools,
                "context_tokens": request.context_token_count,
            },
        )

    def _profile_for_tier(
        self, tier: ModelTier, request: RouterRequest
    ) -> tuple[str, str, bool]:
        """Return (profile_name, provider, tri_attention) for a tier."""
        match tier:
            case ModelTier.T0:
                return "pattern_match", "pattern", False
            case ModelTier.T1:
                return "keyword_classify", "keyword", False
            case ModelTier.T2:
                cfg = self._runtime.get_profile("local-reasoning-qwen3")
                tri = self._tri_attention and (cfg is not None and cfg.tri_attention)
                return "local-reasoning-qwen3", "vllm", tri
            case ModelTier.T3 | _:
                return "cloud_fast_general", "external_api", False

    def _log(self, decision: RoutingDecision, start_ns: int) -> None:
        elapsed_us = (time.monotonic_ns() - start_ns) // 1_000
        logger.info(
            "smart_router_decision",
            tier=decision.tier.name,
            profile=decision.runtime_profile,
            provider=decision.provider,
            tri_attention=decision.tri_attention,
            reason=decision.reason,
            routing_us=elapsed_us,
        )
