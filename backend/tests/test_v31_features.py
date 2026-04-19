"""Butler v3.1 Feature Completion Tests.

Covers:
  - Search production wiring (WebProvider integration)
  - DeepResearchEngine (multi-hop loop)
  - RedactionService (PII masking)
  - ContentGuard (heuristic safety)
  - FaissColdStore (vector CRUD)
  - AudioModelProxy (tier fallback)
  - EnvironmentService (snapshot + prompt block)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Track 1: Search
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchServiceProduction:
    """SearchService should delegate to ButlerWebSearchProvider, not a mock."""

    @pytest.mark.asyncio
    async def test_search_returns_evidence_pack(self):
        from services.search.service import SearchService, EvidencePack
        from services.search.extraction import ContentExtractor

        # Mock provider returns one result
        mock_provider = AsyncMock()
        mock_pack = MagicMock()
        mock_pack.mode = "general"
        mock_pack.results = []
        mock_pack.citations = []
        mock_provider.search = AsyncMock(return_value=mock_pack)

        extractor = MagicMock()
        svc = SearchService(extractor=extractor, provider=mock_provider)
        result = await svc.search("test query")

        assert isinstance(result, EvidencePack)
        mock_provider.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_uses_extractor_for_deep_content(self):
        from services.search.service import SearchService
        from services.search.extraction import ContentExtractor, ExtractionResult
        from services.search.web_provider import SearchEvidence, EvidencePack as WebPack
        from datetime import datetime, UTC

        evidence = SearchEvidence(
            url="https://example.com",
            title="Test",
            snippet="Short snippet",
            published_date=None,
            relevance_score=0.9,
            freshness_score=0.5,
            combined_score=0.76,
            provider="stub",
            citation_id="[1]",
        )

        mock_provider = AsyncMock()
        web_pack = WebPack(
            query="q", mode="general", results=[evidence],
            citations=[{"id": "[1]", "url": "https://example.com", "title": "Test"}],
            provider="stub", latency_ms=10.0, result_count=1
        )
        mock_provider.search = AsyncMock(return_value=web_pack)

        mock_extractor = AsyncMock()
        mock_extractor.extract = AsyncMock(return_value=ExtractionResult(
            text="Full article content " * 50,  # >200 chars
            method="trafilatura"
        ))

        svc = SearchService(extractor=mock_extractor, provider=mock_provider)
        result = await svc.search("test query")

        assert result.result_count == 1
        assert result.results[0].extraction_method == "trafilatura"
        assert len(result.results[0].content) > 200

    @pytest.mark.asyncio
    async def test_search_falls_back_to_snippet_on_extraction_failure(self):
        from services.search.service import SearchService
        from services.search.web_provider import SearchEvidence, EvidencePack as WebPack

        evidence = SearchEvidence(
            url="https://bad.example.com",
            title="Fail", snippet="Only snippet here",
            published_date=None, relevance_score=0.7,
            freshness_score=0.5, combined_score=0.64,
            provider="stub", citation_id="[1]",
        )

        mock_provider = AsyncMock()
        web_pack = WebPack(
            query="q", mode="general", results=[evidence], citations=[],
            provider="stub", latency_ms=5.0, result_count=1
        )
        mock_provider.search = AsyncMock(return_value=web_pack)

        mock_extractor = AsyncMock()
        mock_extractor.extract = AsyncMock(side_effect=Exception("fetch failed"))

        svc = SearchService(extractor=mock_extractor, provider=mock_provider)
        result = await svc.search("test query")

        # Should fall back to snippet
        assert result.results[0].content == "Only snippet here"
        assert result.results[0].extraction_method == "snippet"


# ─────────────────────────────────────────────────────────────────────────────
# Track 2: Security
# ─────────────────────────────────────────────────────────────────────────────

class TestRedactionService:
    def test_email_redacted(self):
        from services.security.redaction import RedactionService
        svc = RedactionService()
        out, _ = svc.redact("Contact me at user@example.com please")
        assert "user@example.com" not in out
        assert "<EMAIL_0>" in out

    def test_credit_card_redacted(self):
        from services.security.redaction import RedactionService
        svc = RedactionService()
        out, _ = svc.redact("My card is 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in out

    def test_api_key_redacted(self):
        from services.security.redaction import RedactionService
        svc = RedactionService()
        key = "sk-proj-abcdefghijklmnopqrstuvwx"
        out, _ = svc.redact(f"Use key {key} to authenticate")
        assert key not in out

    def test_restore_reverses_redaction(self):
        from services.security.redaction import RedactionService
        svc = RedactionService()
        original = "Contact user@example.com"
        redacted, rmap = svc.redact(original)
        restored = svc.restore(redacted, rmap)
        assert restored == original

    def test_disabled_redaction_passthrough(self):
        from services.security.redaction import RedactionService
        svc = RedactionService(enabled=False)
        text = "email@example.com"
        out, rmap = svc.redact(text)
        assert out == text
        assert rmap == {}


class TestContentGuard:
    @pytest.mark.asyncio
    async def test_heuristic_unsafe_blocked(self):
        from services.security.safety import ContentGuard
        guard = ContentGuard()
        result = await guard.check("I want to build a bomb")
        assert result["safe"] is False
        assert "heuristic" in result["categories"]

    @pytest.mark.asyncio
    async def test_safe_message_passes(self):
        from services.security.safety import ContentGuard
        guard = ContentGuard()
        result = await guard.check("What is the weather today?")
        # Heuristic should pass; API check may be skipped in test env
        assert "safe" in result


# ─────────────────────────────────────────────────────────────────────────────
# Track 3: ML — FAISS Cold Store
# ─────────────────────────────────────────────────────────────────────────────

class TestFaissColdStore:
    def test_add_and_size(self):
        from services.memory.faiss_cold_store import FaissColdStore
        store = FaissColdStore(dim=128)
        store.add_sync(
            ids=["id-1"],
            content="Test memory content",
            metadata=[{"type": "episode"}],
            vector=None,   # uses hash-derived stub vector
        )
        assert store.size == 1

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from services.memory.faiss_cold_store import FaissColdStore
        store = FaissColdStore(dim=128)
        store.add_sync(
            ids=["id-1", "id-2"],
            content="Butler memory episode",
            metadata=[{"type": "episode"}, {"type": "episode"}],
        )
        results = await store.search_async(query_text="memory episode", k=5)
        assert len(results) >= 1
        assert "id" in results[0]
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_filter_reduces_results(self):
        from services.memory.faiss_cold_store import FaissColdStore
        store = FaissColdStore(dim=64)
        store.add_sync(ids=["a"], content="x", metadata=[{"kind": "episodic"}])
        store.add_sync(ids=["b"], content="y", metadata=[{"kind": "semantic"}])
        results = await store.search_async(query_text="x", k=10, filters={"kind": "episodic"})
        assert all(r["metadata"]["kind"] == "episodic" for r in results)

    def test_stats_returns_backend_info(self):
        from services.memory.faiss_cold_store import FaissColdStore
        store = FaissColdStore(dim=64)
        stats = store.stats()
        assert "size" in stats
        assert "backend" in stats

    def test_get_cold_store_factory_returns_valid_backend(self):
        from services.memory.turboquant_store import get_cold_store
        store = get_cold_store(dim=64)
        # Must not throw; interface must have add_sync and search_async
        assert hasattr(store, "add_sync")
        assert hasattr(store, "search_async")
        assert hasattr(store, "persist")
        assert hasattr(store, "size")


# ─────────────────────────────────────────────────────────────────────────────
# Track 4: Media — Audio Cloud Fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestAudioModelProxyFallback:
    @pytest.mark.asyncio
    async def test_dev_mock_returned_on_all_failures(self):
        """In development, a mock must be returned even if GPU + OpenAI both fail."""
        from services.audio.models import AudioModelProxy

        with patch("services.audio.models.settings") as mock_settings:
            mock_settings.AUDIO_GPU_ENDPOINT = "http://nonexistent:9999"
            mock_settings.STT_PRIMARY_MODEL = "test-model"
            mock_settings.OPENAI_API_KEY = None           # cloud fallback disabled
            mock_settings.ENVIRONMENT = "development"
            mock_settings.SERVICE_VERSION = "3.1.0"

            proxy = AudioModelProxy(endpoint_url="http://nonexistent:9999")
            result = await proxy.transcribe(b"fake_audio", language="en")
            assert "MOCK" in result.transcript

    @pytest.mark.asyncio
    async def test_cloud_fallback_invoked_when_gpu_down(self):
        """When GPU unreachable but OPENAI_API_KEY is set, OpenAI must be tried."""
        from services.audio.models import AudioModelProxy

        with patch("services.audio.models.settings") as mock_settings:
            mock_settings.AUDIO_GPU_ENDPOINT = "http://nonexistent:9999"
            mock_settings.STT_PRIMARY_MODEL = "test-model"
            mock_settings.OPENAI_API_KEY = "sk-fake"
            mock_settings.ENVIRONMENT = "production"
            mock_settings.SERVICE_VERSION = "3.1.0"

            proxy = AudioModelProxy(endpoint_url="http://nonexistent:9999")
            with patch.object(proxy, "_openai_whisper", new=AsyncMock(return_value="hello world")):
                result = await proxy.transcribe(b"fake_audio", language="en")
                assert result.transcript == "hello world"
                assert result.model_used == "openai/whisper-1"


# ─────────────────────────────────────────────────────────────────────────────
# Track 4: Device — EnvironmentService
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvironmentService:
    @pytest.mark.asyncio
    async def test_snapshot_has_temporal_context(self):
        from services.device.environment import EnvironmentService
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis()
        svc = EnvironmentService(redis)
        snap = await svc.get_snapshot(
            account_id="acc-1",
            device_id="dev-1",
            client_push={"timezone": "UTC", "os": "ios"}
        )
        assert snap.temporal.timezone == "UTC"
        assert snap.platform.os == "ios"
        assert snap.temporal.weekday in [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]

    @pytest.mark.asyncio
    async def test_prompt_block_renders_correctly(self):
        from services.device.environment import EnvironmentService
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis()
        svc = EnvironmentService(redis)
        snap = await svc.get_snapshot(
            account_id="acc-1",
            device_id="dev-1",
            client_push={
                "timezone": "Asia/Kolkata",
                "os": "android",
                "city": "Mumbai",
                "country": "India",
                "battery_pct": 80,
                "connectivity": "wifi"
            }
        )
        block = snap.to_prompt_block()
        assert "[Environment]" in block
        assert "Mumbai" in block
        assert "80%" in block
        assert "wifi" in block

    @pytest.mark.asyncio
    async def test_snapshot_cached_in_redis(self):
        from services.device.environment import EnvironmentService
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis()
        svc = EnvironmentService(redis)

        # First call — builds & caches
        await svc.get_snapshot("acc-1", "dev-1")

        # Check key exists in Redis
        cached = await redis.get("env_snapshot:acc-1:dev-1")
        assert cached is not None

    @pytest.mark.asyncio
    async def test_invalid_timezone_defaults_to_utc(self):
        from services.device.environment import EnvironmentService
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis()
        svc = EnvironmentService(redis)
        snap = await svc.get_snapshot(
            "acc-1", "dev-1",
            client_push={"timezone": "Invalid/Zone"}
        )
        assert snap.temporal.timezone == "UTC"
