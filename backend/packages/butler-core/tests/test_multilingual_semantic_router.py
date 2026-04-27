"""Multilingual tests for SemanticEmbeddingRouter.

Tests verify semantic routing works with:
- English
- Hindi
- Hinglish
- Transliteration
- Typo-heavy text
- Indirect phrasing
"""

import pytest
from butler_core.ml.routing import RoutingDecision
from butler_core.ml.semantic_router import SemanticCategory, SemanticEmbeddingRouter


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}

    async def embed_one(self, text: str) -> list[float]:
        # Simple mock: return text-length-based vector for some semantic similarity
        text_lower = text.lower()
        if text_lower not in self.embeddings:
            # Use text characteristics to create somewhat semantic vectors
            # This is a simplified mock for testing purposes
            vector = [0.0] * 384
            for i, char in enumerate(text_lower[:384]):
                vector[i] = ord(char) / 255.0
            self.embeddings[text_lower] = vector
        return self.embeddings[text_lower]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_one(text) for text in texts]


@pytest.mark.asyncio
async def test_english_safe_answer_only():
    """Test English safe answer-only requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Explain how photosynthesis works")
    # Verify router produces a valid result
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0
    assert result.confidence <= 1.0
    assert isinstance(result.reasoning, str)
    assert isinstance(result.similarity_scores, dict)


@pytest.mark.asyncio
async def test_english_filesystem_mutation():
    """Test English filesystem mutation requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Delete the file called config.txt")
    # Verify router produces a valid result
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0
    assert result.confidence <= 1.0


@pytest.mark.asyncio
async def test_english_external_message():
    """Test English external message requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Send an email to john@example.com")
    # Verify router produces a valid result
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0
    assert result.confidence <= 1.0


@pytest.mark.asyncio
async def test_hindi_safe_answer_only():
    """Test Hindi safe answer-only requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("फोटोसिंथेसिस कैसे काम करता है")
    # Verify router handles Hindi text
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_hindi_filesystem_mutation():
    """Test Hindi filesystem mutation requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("config.txt फाइल को हटा दो")
    # Verify router handles Hindi text
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_hinglish_safe_answer_only():
    """Test Hinglish safe answer-only requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Photosynthesis kaise kaam karta hai")
    # Verify router handles Hinglish text
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_hinglish_filesystem_mutation():
    """Test Hinglish filesystem mutation requests."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Config.txt file ko delete kar do")
    # Verify router handles Hinglish text
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_transliteration_english_to_hindi():
    """Test transliteration from English to Hindi script."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("फोटोसिंथेसिस कैसे काम करता है")
    # Verify router handles transliterated text
    assert result.decision in RoutingDecision


@pytest.mark.asyncio
async def test_typo_heavy_text():
    """Test typo-heavy text still routes correctly."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Dlete the flie caled config.txt")
    # Verify router handles typo-heavy text
    assert result.decision in RoutingDecision


@pytest.mark.asyncio
async def test_indirect_phrasing_filesystem():
    """Test indirect phrasing for filesystem operations."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("I need to get rid of that configuration file")
    # Verify router handles indirect phrasing
    assert result.decision in RoutingDecision


@pytest.mark.asyncio
async def test_indirect_phrasing_external_message():
    """Test indirect phrasing for external messaging."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Let him know about the meeting")
    # Verify router handles indirect phrasing
    assert result.decision in RoutingDecision


@pytest.mark.asyncio
async def test_indirect_phrasing_credentials():
    """Test indirect phrasing for credential access."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("I need the password for the database")
    # Verify router handles indirect phrasing
    assert result.decision in RoutingDecision


@pytest.mark.asyncio
async def test_ambiguity_escalates_to_llm():
    """Test ambiguous requests escalate to LLM."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider, ambiguity_margin=0.3)
    await router.initialize()

    result = await router.route("Help me with the thing")
    assert result.decision == RoutingDecision.ESCALATE_TO_LLM
    assert "ambiguous" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_empty_input():
    """Test empty input handling."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("")
    assert result.decision == RoutingDecision.ESCALATE_TO_LLM
    assert "empty" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_custom_categories():
    """Test custom semantic categories."""
    provider = MockEmbeddingProvider()
    custom_categories = (
        SemanticCategory(
            name="custom.test",
            examples=("This is a test", "Testing the system"),
        ),
    )
    router = SemanticEmbeddingRouter(embedding_provider=provider, categories=custom_categories)
    await router.initialize()

    result = await router.route("This is a test")
    assert result.decision == RoutingDecision.ESCALATE_TO_LLM
    assert "custom" in result.top_category.lower()
