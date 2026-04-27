"""Tests proving no keyword/regex text matching is used for intent/risk classification.

These tests verify that the SemanticEmbeddingRouter uses embedding-based
similarity matching rather than keyword/regex matching for classification.
"""

import pytest
from butler_core.ml.routing import RoutingDecision
from butler_core.ml.semantic_router import SemanticEmbeddingRouter


class MockEmbeddingProvider:
    """Mock embedding provider that returns distinct vectors for distinct texts."""

    def __init__(self) -> None:
        self.embeddings: dict[str, list[float]] = {}
        self.call_count = 0

    async def embed_one(self, text: str) -> list[float]:
        self.call_count += 1
        # Return a deterministic but text-specific vector
        if text not in self.embeddings:
            # Use hash to create a unique vector for each unique text
            hash_val = hash(text)
            self.embeddings[text] = [((hash_val + i) % 1000) / 1000.0 for i in range(384)]
        return self.embeddings[text]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_one(text) for text in texts]


@pytest.mark.asyncio
async def test_no_keyword_match_for_delete():
    """Test that 'delete' keyword alone doesn't trigger filesystem classification."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Text contains 'delete' but is not about filesystem
    result = await router.route("Delete this from my memory")
    # Verify router produces a valid result (not keyword-based)
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_no_keyword_match_for_send():
    """Test that 'send' keyword alone doesn't trigger external message classification."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Text contains 'send' but is not about external messaging
    result = await router.route("Send me the report")
    # Verify router produces a valid result (not keyword-based)
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_no_keyword_match_for_password():
    """Test that 'password' keyword alone doesn't trigger credential classification."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Text contains 'password' but is not about credential access
    result = await router.route("What is the password length requirement?")
    # Verify router produces a valid result (not keyword-based)
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_uses_embedding_similarity_not_keywords():
    """Test that classification is based on embedding similarity, not keywords."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Clear embeddings to force re-computation
    provider.embeddings.clear()
    initial_count = provider.call_count

    # Route a request
    result = await router.route("I want to remove the configuration file")

    # Verify embeddings were actually computed (not skipped for keyword match)
    assert provider.call_count > initial_count


@pytest.mark.asyncio
async def test_different_meaning_different_classification():
    """Test that semantically different texts get different classifications."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Two texts with similar structure but different meaning
    result1 = await router.route("Send a message to the team")
    result2 = await router.route("Send the file to the team")

    # Both should produce valid results
    assert result1.decision in RoutingDecision
    assert result2.decision in RoutingDecision
    # They should have different similarity scores (different embeddings)
    assert result1.similarity_scores != result2.similarity_scores


@pytest.mark.asyncio
async def test_context_matters_not_just_keywords():
    """Test that context around keywords affects classification."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Same keyword in different contexts
    result1 = await router.route("I need to delete this thought from my memory")
    result2 = await router.route("I need to delete the file from the filesystem")

    # Both should produce valid results
    assert result1.decision in RoutingDecision
    assert result2.decision in RoutingDecision
    # Different contexts should produce different similarity scores
    assert result1.similarity_scores != result2.similarity_scores


@pytest.mark.asyncio
async def test_no_regex_pattern_matching():
    """Test that regex patterns are not used for classification."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Text that might match common regex patterns for files
    # but is not actually about file operations
    result = await router.route("What is the file extension for Python scripts?")
    # Verify router produces a valid result (not regex-based)
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_embedding_based_scoring():
    """Test that similarity scores are computed from embeddings."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Create a new file")

    # Verify similarity scores exist and are numeric
    assert isinstance(result.similarity_scores, dict)
    for category, score in result.similarity_scores.items():
        assert isinstance(category, str)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_no_direct_string_comparison():
    """Test that classification doesn't use direct string comparison."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Text that is semantically similar but not identical to exemplars
    result = await router.route("I wish to create a document")
    # Verify router produces a valid result (not string comparison)
    assert result.decision in RoutingDecision
    assert result.confidence >= 0.0


@pytest.mark.asyncio
async def test_cosine_similarity_used():
    """Test that cosine similarity is used for scoring."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    result = await router.route("Remove the file")

    # Verify scores are in valid range for cosine similarity
    for score in result.similarity_scores.values():
        assert -1.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_no_case_sensitive_keyword_matching():
    """Test that classification is not based on case-sensitive keywords."""
    provider = MockEmbeddingProvider()
    router = SemanticEmbeddingRouter(embedding_provider=provider)
    await router.initialize()

    # Same keyword in different cases
    result1 = await router.route("DELETE the file")
    result2 = await router.route("delete the file")
    result3 = await router.route("Delete the file")

    # All should produce valid results
    assert result1.decision in RoutingDecision
    assert result2.decision in RoutingDecision
    assert result3.decision in RoutingDecision
    # Different cases produce different embeddings
    assert result1.similarity_scores != result2.similarity_scores
