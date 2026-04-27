"""Comprehensive tests for ContentGuard safety checker.

Tests cover:
- ContentGuard initialization
- Safety check with semantic classifier
- Safety check fallback to OpenAI API
- Error handling and edge cases
- Hardened error handling
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.security.safety import ContentGuard


class TestContentGuard:
    """Test ContentGuard initialization and configuration."""

    def test_init_with_tenant_id(self):
        """Test ContentGuard initialization with tenant_id."""
        guard = ContentGuard(tenant_id="tenant_1")
        assert guard.provider == "openai"
        assert guard._tenant_id == "tenant_1"
        assert guard._semantic_classifier is None
        assert guard._safe_client is not None
        assert guard._client is not None

    def test_init_without_tenant_id(self):
        """Test ContentGuard initialization without tenant_id."""
        guard = ContentGuard()
        assert guard._tenant_id is None
        assert guard._safe_client is None
        assert guard._client is not None

    def test_init_with_custom_provider(self):
        """Test ContentGuard initialization with custom provider."""
        guard = ContentGuard(provider="anthropic", tenant_id="tenant_1")
        assert guard.provider == "anthropic"

    def test_init_with_semantic_classifier(self):
        """Test ContentGuard initialization with semantic classifier."""
        mock_classifier = MagicMock()
        guard = ContentGuard(semantic_classifier=mock_classifier)
        assert guard._semantic_classifier is mock_classifier


class TestSafetyCheck:
    """Test safety check functionality."""

    @pytest.mark.asyncio
    async def test_check_with_semantic_classifier(self):
        """Test safety check using semantic classifier."""
        # Mock semantic classifier
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        result = await guard.check("This is safe text")

        assert result["safe"] is True
        assert result["reason"] is None
        assert result["categories"]["risk_level"] == "low"
        assert result["categories"]["confidence"] == 0.95
        mock_classifier.classify_safety.assert_called_once_with("This is safe text")

    @pytest.mark.asyncio
    async def test_check_with_semantic_classifier_unsafe(self):
        """Test safety check with semantic classifier detecting unsafe content."""
        # Mock semantic classifier
        mock_classification = MagicMock()
        mock_classification.is_safe = False
        mock_classification.reasoning = "Detected hate speech"
        mock_classification.risk_level = MagicMock(value="high")
        mock_classification.categories = [MagicMock(value="hate_speech")]
        mock_classification.confidence = 0.98
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        result = await guard.check("This is hate speech")

        assert result["safe"] is False
        assert result["reason"] == "Detected hate speech"
        assert result["categories"]["risk_level"] == "high"
        assert "hate_speech" in result["categories"]["detected_categories"]

    @pytest.mark.asyncio
    async def test_check_semantic_classifier_failure_fallback(self):
        """Test fallback when semantic classifier fails."""
        # Mock semantic classifier that raises exception
        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.side_effect = Exception("Classification failed")

        # Mock OpenAI API response
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"results": [{"flagged": False, "categories": {}}]}

            guard = ContentGuard(semantic_classifier=mock_classifier)
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await guard.check("Test text")

                # Should fallback to API and return safe
                assert result["safe"] is True

    @pytest.mark.asyncio
    async def test_check_development_mode_no_api_key(self):
        """Test safety check in development mode without API key."""
        from infrastructure.config import settings

        with patch.object(settings, "ENVIRONMENT", "development"):
            with patch.dict(os.environ, {}, clear=True):
                guard = ContentGuard()
                result = await guard.check("Test text")

                # Should return safe in development mode
                assert result["safe"] is True
                assert result["reason"] == "Development mode - no API key"

    @pytest.mark.asyncio
    async def test_check_openai_api_flagged(self):
        """Test safety check with OpenAI API flagging content."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "results": [
                    {
                        "flagged": True,
                        "categories": {"hate": True, "violence": False},
                    }
                ]
            }

            guard = ContentGuard()
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await guard.check("Hate speech text")

                assert result["safe"] is False
                assert result["reason"] == "Flagged by Moderation API"
                assert result["categories"]["hate"] is True

    @pytest.mark.asyncio
    async def test_check_openai_api_safe(self):
        """Test safety check with OpenAI API returning safe."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"results": [{"flagged": False, "categories": {}}]}

            guard = ContentGuard()
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await guard.check("Safe text")

                assert result["safe"] is True
                assert result["reason"] is None

    @pytest.mark.asyncio
    async def test_check_api_error_fail_safe(self):
        """Test safety check fails safe on API error."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            guard = ContentGuard()
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = Exception("API error")

                result = await guard.check("Test text")

                # Should fail safe
                assert result["safe"] is True
                assert result["reason"] == "Bypassed due to API error"

    @pytest.mark.asyncio
    async def test_check_empty_text(self):
        """Test safety check with empty text."""
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        result = await guard.check("")

        assert result["safe"] is True

    @pytest.mark.asyncio
    async def test_check_very_long_text(self):
        """Test safety check with very long text."""
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        long_text = "Safe text " * 10000  # Very long text
        result = await guard.check(long_text)

        assert result["safe"] is True

    @pytest.mark.asyncio
    async def test_check_unicode_text(self):
        """Test safety check with unicode text."""
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        unicode_text = "Safe text 日本語 中文 العربية"
        result = await guard.check(unicode_text)

        assert result["safe"] is True


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_check_semantic_classifier_exception(self):
        """Test handling semantic classifier exception."""
        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.side_effect = RuntimeError("Classifier error")

        with patch.dict(os.environ, {}, clear=True):
            from infrastructure.config import settings

            with patch.object(settings, "ENVIRONMENT", "development"):
                guard = ContentGuard(semantic_classifier=mock_classifier)
                result = await guard.check("Test text")

                # Should fallback to development mode
                assert result["safe"] is True

    @pytest.mark.asyncio
    async def test_check_api_timeout(self):
        """Test handling API timeout."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            guard = ContentGuard()
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.side_effect = TimeoutError("API timeout")

                result = await guard.check("Test text")

                # Should fail safe
                assert result["safe"] is True
                assert result["reason"] == "Bypassed due to API error"

    @pytest.mark.asyncio
    async def test_check_api_invalid_response(self):
        """Test handling invalid API response."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.side_effect = Exception("Invalid JSON")

            guard = ContentGuard()
            with patch.object(guard._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_response

                result = await guard.check("Test text")

                # Should fail safe
                assert result["safe"] is True
                assert result["reason"] == "Bypassed due to API error"

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing the HTTP client."""
        guard = ContentGuard()
        await guard.close()
        # Should not raise any exception


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_safety_flow_with_classifier(self):
        """Test full safety flow with semantic classifier."""
        mock_classification = MagicMock()
        mock_classification.is_safe = False
        mock_classification.reasoning = "Violent content detected"
        mock_classification.risk_level = MagicMock(value="high")
        mock_classification.categories = [MagicMock(value="violence")]
        mock_classification.confidence = 0.92
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        result = await guard.check("Violent text")

        assert result["safe"] is False
        assert result["reason"] == "Violent content detected"
        assert result["categories"]["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_multiple_sequential_checks(self):
        """Test multiple sequential safety checks."""
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)

        texts = ["Text 1", "Text 2", "Text 3"]
        results = [await guard.check(text) for text in texts]

        # All should be safe
        assert all(r["safe"] for r in results)
        assert mock_classifier.classify_safety.call_count == 3

    @pytest.mark.asyncio
    async def test_check_with_special_characters(self):
        """Test safety check with special characters."""
        mock_classification = MagicMock()
        mock_classification.is_safe = True
        mock_classification.reasoning = None
        mock_classification.risk_level = MagicMock(value="low")
        mock_classification.categories = []
        mock_classification.confidence = 0.95
        mock_classification.language = "en"

        mock_classifier = AsyncMock()
        mock_classifier.classify_safety.return_value = mock_classification

        guard = ContentGuard(semantic_classifier=mock_classifier)
        special_text = "Safe text with <script> tags and & symbols"
        result = await guard.check(special_text)

        assert result["safe"] is True
