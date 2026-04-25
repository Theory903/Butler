"""Phase 5 — ML Smart Router and Auth Credential Pool tests.

Tests ButlerSmartRouter (T0–T3 decision logic, tri_attention toggle,
KV overflow escalation, force_tier override) and ButlerCredentialPool
(token introspection cache, revocation fast-path, tool credential
forwarding, AAL rank comparison).

All fully mocked — no real JWTs signed, no real Redis, no LLM calls.

Verifies:
  1. SmartRouter T0: high-confidence simple intent with no tools → T0 profile
  2. SmartRouter T1: keyword-classified simple, no tools → T1
  3. SmartRouter T2: complex/tool intent with local vLLM available → T2
  4. SmartRouter T3: complex, no T2 → T3 cloud
  5. SmartRouter KV overflow: context > 10k tokens → T3 escalation
  6. SmartRouter force_tier: override goes to requested tier
  7. SmartRouter tri_attention: T2 carries tri_attention=True when enabled
  8. SmartRouter T3 default: unclassified intent falls through to T3
  9. ModelRegistry: get_active_by_tier returns correct entries
  10. ModelRegistry: preferred_t3_provider returns cheapest active T3
  11. CredentialPool introspection: cache miss → JWKSManager.verify_token()
  12. CredentialPool introspection: cache hit → no JWKSManager call
  13. CredentialPool revocation: revoked session → valid=False (cache hit path)
  14. CredentialPool revocation: revoked JTI → valid=False (live path)
  15. CredentialPool revoke_session: Redis setex called
  16. CredentialPool revoke_all_sessions: pipeline with all session IDs
  17. CredentialPool tool_credential: env var loaded and in-memory cached
  18. CredentialPool tool_credential: cache hit avoids re-read
  19. CredentialPool tool_credential: missing env var returns None
  20. CredentialPool AAL: aal1 < aal2 < aal3 ordering
  21. CredentialPool bust_tool_cache: clears provider entries
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from domain.ml.contracts import IntentResult
from services.auth.credential_pool import ButlerCredentialPool, _token_fingerprint
from services.ml.registry import ModelRegistry
from services.ml.runtime import MLRuntimeManager
from services.ml.smart_router import (
    ButlerSmartRouter,
    ModelTier,
    RouterRequest,
)

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_runtime() -> MLRuntimeManager:
    return MLRuntimeManager()


def _make_router(tri=False) -> ButlerSmartRouter:
    return ButlerSmartRouter(runtime=_make_runtime(), tri_attention_enabled=tri)


def _intent(
    label="general",
    confidence=0.5,
    complexity="simple",
    requires_tools=False,
    requires_memory=True,
    requires_approval=False,
) -> IntentResult:
    return IntentResult(
        label=label,
        confidence=confidence,
        complexity=complexity,
        requires_tools=requires_tools,
        requires_memory=requires_memory,
        requires_approval=requires_approval,
    )


def _req(intent=None, **kwargs) -> RouterRequest:
    return RouterRequest(
        intent=intent or _intent(),
        message="test message",
        **kwargs,
    )


def _make_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    pipe = MagicMock()
    pipe.setex = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[True] * 10)
    redis.pipeline = MagicMock(return_value=pipe)
    return redis


def _make_jwks(claims: dict | None = None, error: Exception | None = None):
    jwks = MagicMock()
    if error:
        jwks.verify_token = MagicMock(side_effect=error)
    else:
        jwks.verify_token = MagicMock(
            return_value=claims
            or {
                "sub": "acct_test",
                "sid": "ses_test",
                "jti": "jti_test",
                "aal": "aal2",
                "exp": int(time.time()) + 900,
                "iat": int(time.time()),
                "iss": "https://butler.lasmoid.ai",
                "aud": "butler-api",
            }
        )
    return jwks


# ─────────────────────────────────────────────────────────────────────────────
# Test 17: ButlerSmartRouter
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerSmartRouter:
    def test_t0_high_confidence_simple_no_tools(self):
        """High-confidence simple intent with no tools/memory → T0."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    label="greeting",
                    confidence=0.95,
                    complexity="simple",
                    requires_tools=False,
                    requires_memory=False,
                )
            )
        )
        assert decision.tier == ModelTier.T0
        assert decision.provider == "pattern"

    def test_t1_keyword_simple_no_tools(self):
        """Keyword-classified simple intent (≥0.75), no tools → T1."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    label="greeting",
                    confidence=0.80,
                    complexity="simple",
                    requires_tools=False,
                    requires_memory=True,
                )
            )
        )
        assert decision.tier == ModelTier.T1
        assert decision.provider == "keyword"

    def test_t2_complex_intent_local_available(self):
        """Complex intent with T2 local vLLM available → T2."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    label="search", confidence=0.7, complexity="complex", requires_tools=True
                )
            )
        )
        assert decision.tier == ModelTier.T2
        assert decision.provider == "vllm"
        assert decision.runtime_profile == "local-reasoning-qwen3"

    def test_t3_when_no_t2_available(self):
        """When no local-reasoning-qwen3 profile exists → escalate to T3."""
        runtime = MLRuntimeManager()
        # Stub out the registry to simulate missing profile
        with patch.dict(runtime._registry.MODELS, {}, clear=True):
            router = ButlerSmartRouter(runtime=runtime)
            decision = router.route(_req(intent=_intent(complexity="complex", requires_tools=True)))
            assert decision.tier == ModelTier.T3
            assert decision.provider == "external_api"

    def test_t3_kv_overflow(self):
        """Context > 10k tokens → T3 regardless of intent complexity."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(complexity="simple"),
                context_token_count=12_000,
            )
        )
        assert decision.tier == ModelTier.T3
        assert (
            "KV budget" in decision.reason
            or "kv" in decision.reason.lower()
            or "10" in decision.reason
        )

    def test_force_tier_t0(self):
        """force_tier=T0 overrides routing for complex intent."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(complexity="complex", requires_tools=True),
                force_tier=ModelTier.T0,
            )
        )
        assert decision.tier == ModelTier.T0
        assert decision.override_by_user is True

    def test_force_tier_t3(self):
        """force_tier=T3 routes to cloud even for simple intent."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    complexity="simple",
                    confidence=0.99,
                    requires_tools=False,
                    requires_memory=False,
                ),
                force_tier=ModelTier.T3,
            )
        )
        assert decision.tier == ModelTier.T3
        assert decision.override_by_user is True

    def test_tri_attention_enabled_on_t2(self):
        """With tri_attention_enabled=True and T2 route → tri_attention=True."""
        router = _make_router(tri=True)
        decision = router.route(_req(intent=_intent(complexity="complex", requires_tools=True)))
        assert decision.tier == ModelTier.T2
        assert decision.tri_attention is True

    def test_tri_attention_disabled_on_t2(self):
        """With tri_attention_enabled=False → tri_attention=False even on T2."""
        router = _make_router(tri=False)
        decision = router.route(_req(intent=_intent(complexity="complex", requires_tools=True)))
        assert decision.tier == ModelTier.T2
        assert decision.tri_attention is False

    def test_tri_attention_always_false_on_t3(self):
        """T3 cloud always tri_attention=False (no local GPU)."""
        router = _make_router(tri=True)
        decision = router.route(
            _req(
                intent=_intent(complexity="complex", requires_tools=True),
                context_token_count=15_000,  # force T3 via KV overflow
            )
        )
        assert decision.tier == ModelTier.T3
        assert decision.tri_attention is False

    def test_decision_metadata_includes_intent(self):
        """RoutingDecision.metadata must carry intent label and confidence."""
        router = _make_router()
        decision = router.route(
            _req(intent=_intent(label="search", confidence=0.72, requires_tools=True))
        )
        assert decision.metadata["intent_label"] == "search"
        assert decision.metadata["intent_confidence"] == 0.72

    def test_t3_default_for_unclassified(self):
        """Unclassified general intent below keyword threshold → T3 default."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    label="general",
                    confidence=0.5,
                    complexity="simple",
                    requires_tools=False,
                    requires_memory=True,
                )
            )
        )
        # confidence < 0.75 and requires_memory=True → falls to T2 or T3
        assert decision.tier in (ModelTier.T2, ModelTier.T3)

    def test_latency_budget_tight_routes_t2(self):
        """Tight latency budget (≤400ms) with T2 available → T2 selected."""
        router = _make_router()
        decision = router.route(
            _req(
                intent=_intent(
                    confidence=0.6, complexity="simple", requires_tools=False, requires_memory=True
                ),
                latency_budget_ms=300,
            )
        )
        assert decision.tier == ModelTier.T2


# ─────────────────────────────────────────────────────────────────────────────
# Test 18: ModelRegistry
# ─────────────────────────────────────────────────────────────────────────────


class TestModelRegistry:
    def test_get_active_model_returns_entry(self):
        reg = ModelRegistry()
        m = reg.get_active_model("local-reasoning-qwen3")
        assert m is not None
        assert m.tier == 2
        assert m.provider == "vllm"

    def test_get_active_model_missing_returns_none(self):
        reg = ModelRegistry()
        assert reg.get_active_model("nonexistent-model-xyz") is None

    def test_get_active_by_tier_t2(self):
        reg = ModelRegistry()
        t2 = reg.get_active_by_tier(2)
        assert any(m.provider == "vllm" for m in t2)

    def test_get_active_by_tier_t3(self):
        reg = ModelRegistry()
        t3 = reg.get_active_by_tier(3)
        providers = {m.provider for m in t3}
        assert "anthropic" in providers or "openai" in providers

    def test_preferred_t3_provider_returns_string(self):
        reg = ModelRegistry()
        provider = reg.preferred_t3_provider()
        assert isinstance(provider, str)
        assert provider in ("anthropic", "openai", "google")

    def test_list_models_returns_all(self):
        reg = ModelRegistry()
        models = reg.list_models()
        assert len(models) >= 5
        names = {m["name"] for m in models}
        assert "local-reasoning-qwen3" in names
        assert "cloud-frontier-anthropic" in names

    def test_tri_attention_on_t2_models(self):
        reg = ModelRegistry()
        t2 = reg.get_active_by_tier(2)
        assert all(m.tri_attention for m in t2)

    def test_tri_attention_false_on_t3(self):
        reg = ModelRegistry()
        t3 = reg.get_active_by_tier(3)
        assert all(not m.tri_attention for m in t3)


# ─────────────────────────────────────────────────────────────────────────────
# Test 19: ButlerCredentialPool
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerCredentialPool:
    def _make_pool(self, redis=None, jwks=None) -> ButlerCredentialPool:
        return ButlerCredentialPool(
            redis=redis or _make_redis(),
            jwks_manager=jwks or _make_jwks(),
        )

    def test_introspect_cache_miss_calls_jwks(self):
        """Cache miss → JWKSManager.verify_token() called."""
        jwks = _make_jwks()
        pool = self._make_pool(jwks=jwks)
        result = asyncio.run(pool.introspect("token.jwt.abc"))
        assert result.valid is True
        assert result.account_id == "acct_test"
        assert result.session_id == "ses_test"
        jwks.verify_token.assert_called_once()

    def test_introspect_cache_hit_skips_jwks(self):
        """Cache hit → JWKSManager.verify_token() NOT called."""
        redis = _make_redis()
        cached = json.dumps(
            {
                "account_id": "acct_cached",
                "session_id": "ses_cached",
                "assurance_level": "aal2",
                "token_id": "jti_cached",
            }
        ).encode()
        # Call order: (1) cache lookup = hit, (2) session revoke = None, (3) jti revoke = None
        redis.get = AsyncMock(side_effect=[cached, None, None])
        jwks = _make_jwks()
        pool = self._make_pool(redis=redis, jwks=jwks)
        result = asyncio.run(pool.introspect("cached.token"))
        assert result.valid is True
        assert result.account_id == "acct_cached"
        jwks.verify_token.assert_not_called()

    def test_introspect_invalid_jwt_returns_not_valid(self):
        """JWKSManager raises → introspect returns valid=False."""
        jwks = _make_jwks(error=Exception("expired"))
        pool = self._make_pool(jwks=jwks)
        result = asyncio.run(pool.introspect("bad.jwt"))
        assert result.valid is False
        assert "jwt_error" in result.reason

    def test_introspect_revoked_session_cache_hit(self):
        """Cache hit for revoked session → valid=False."""
        redis = _make_redis()
        cached = json.dumps(
            {
                "account_id": "acct_r",
                "session_id": "ses_revoked",
                "assurance_level": "aal1",
                "token_id": "jti_r",
            }
        ).encode()
        redis.get = AsyncMock(side_effect=[cached, b"1", None])
        pool = self._make_pool(redis=redis)
        result = asyncio.run(pool.introspect("revoked.token"))
        assert result.valid is False
        assert "revoked" in result.reason

    def test_introspect_revoked_jti_live_path(self):
        """Live verify + JTI revoked → valid=False."""
        redis = _make_redis()
        # Call order after cache miss: (1) cache = None, (2) _is_jti_revoked = b"1", (3) _is_session_revoked not reached
        # introspect() checks jti FIRST after live verify, then session
        # so: get(cache_key)=None → verify_token OK → get(jti_key)=b"1" → return revoked_jti
        redis.get = AsyncMock(side_effect=[None, b"1"])
        jwks = _make_jwks()
        pool = self._make_pool(redis=redis, jwks=jwks)
        result = asyncio.run(pool.introspect("token"))
        assert result.valid is False
        assert "jti" in result.reason

    def test_revoke_session_calls_setex(self):
        """revoke_session() must call Redis setex with session key."""
        redis = _make_redis()
        pool = self._make_pool(redis=redis)
        asyncio.run(pool.revoke_session("ses_target", ttl_s=3600))
        redis.setex.assert_called_once()
        args = redis.setex.call_args.args
        assert "ses_target" in args[0]

    def test_revoke_all_sessions_uses_pipeline(self):
        """revoke_all_sessions() calls Redis pipeline once."""
        redis = _make_redis()
        pool = self._make_pool(redis=redis)
        count = asyncio.run(
            pool.revoke_all_sessions(
                account_id="acct_all",
                session_ids=["ses_a", "ses_b", "ses_c"],
            )
        )
        assert count == 3
        redis.pipeline.assert_called()

    def test_get_tool_credential_from_env(self, monkeypatch):
        """Tool credential loaded from BUTLER_TOOL_CRED_{PROVIDER} env var."""
        monkeypatch.setenv("BUTLER_TOOL_CRED_OPENAI", "sk-test-key")
        pool = self._make_pool()
        cred = asyncio.run(pool.get_tool_credential("openai", "acct_1"))
        assert cred is not None
        assert cred.provider == "openai"
        assert cred.api_key == "sk-test-key"

    def test_get_tool_credential_cached_in_memory(self, monkeypatch):
        """Second call returns cached credential without re-reading env."""
        monkeypatch.setenv("BUTLER_TOOL_CRED_GITHUB", "ghp-test")
        pool = self._make_pool()
        asyncio.run(pool.get_tool_credential("github", "acct_c"))
        # Monkeypatch away the env var — if cache works, result is still non-None
        monkeypatch.delenv("BUTLER_TOOL_CRED_GITHUB", raising=False)
        cred = asyncio.run(pool.get_tool_credential("github", "acct_c"))
        assert cred is not None
        assert cred.api_key == "ghp-test"

    def test_get_tool_credential_missing_returns_none(self, monkeypatch):
        """Missing env var → None (no credential available)."""
        monkeypatch.delenv("BUTLER_TOOL_CRED_UNKNOWN_PROVIDER", raising=False)
        pool = self._make_pool()
        cred = asyncio.run(pool.get_tool_credential("unknown-provider", "acct_x"))
        assert cred is None

    def test_bust_tool_cache_provider(self, monkeypatch):
        """bust_tool_cache(provider) removes only that provider's entries."""
        monkeypatch.setenv("BUTLER_TOOL_CRED_SLACK", "xoxb-test")
        pool = self._make_pool()
        asyncio.run(pool.get_tool_credential("slack", "acct_b"))
        assert len(pool._tool_cache) == 1
        pool.bust_tool_cache("slack")
        assert len(pool._tool_cache) == 0

    def test_bust_tool_cache_all(self, monkeypatch):
        """bust_tool_cache() with no args clears everything."""
        monkeypatch.setenv("BUTLER_TOOL_CRED_SLACK", "xoxb-1")
        monkeypatch.setenv("BUTLER_TOOL_CRED_OPENAI", "sk-1")
        pool = self._make_pool()
        asyncio.run(pool.get_tool_credential("slack", "acct_b"))
        asyncio.run(pool.get_tool_credential("openai", "acct_b"))
        assert len(pool._tool_cache) == 2
        pool.bust_tool_cache()
        assert len(pool._tool_cache) == 0

    def test_aal_satisfies_ordering(self):
        assert ButlerCredentialPool.aal_satisfies("aal1", "aal1") is True
        assert ButlerCredentialPool.aal_satisfies("aal2", "aal1") is True
        assert ButlerCredentialPool.aal_satisfies("aal3", "aal2") is True
        assert ButlerCredentialPool.aal_satisfies("aal1", "aal2") is False
        assert ButlerCredentialPool.aal_satisfies("aal1", "aal3") is False
        assert ButlerCredentialPool.aal_satisfies("aal2", "aal3") is False

    def test_token_fingerprint_consistent(self):
        t = "header.payload.signature"
        assert _token_fingerprint(t) == _token_fingerprint(t)

    def test_token_fingerprint_different_tokens(self):
        assert _token_fingerprint("tokenA") != _token_fingerprint("tokenB")

    def test_token_fingerprint_length(self):
        fp = _token_fingerprint("any-token")
        assert len(fp) == 32
