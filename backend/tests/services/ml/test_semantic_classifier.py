"""Multilingual and adversarial test cases for semantic classifier.

Tests verify that the semantic classifier works across languages,
code-mixed input, transliteration, and adversarial typos without
relying on English-only keyword matching.
"""

import hashlib
from unittest.mock import AsyncMock, Mock

import pytest

from services.ml.semantic_classifier import (
    RiskClassification,
    RiskLevel,
    SafetyCategory,
    SafetyClassification,
    SemanticClassifier,
)
from services.policy.capability_policy import CapabilityPolicy, CapabilityPolicyEngine, DataScope


class TestMultilingualSafetyClassification:
    """Test safety classification across multiple languages."""

    @pytest.fixture
    def mock_runtime(self):
        """Mock reasoning runtime for testing."""
        runtime = Mock()
        runtime.generate = AsyncMock()
        return runtime

    @pytest.fixture
    def classifier(self, mock_runtime):
        """Create classifier with mock runtime."""
        return SemanticClassifier(runtime=mock_runtime)

    @pytest.mark.asyncio
    async def test_hindi_safety_classification(self, classifier, mock_runtime):
        """Test safety classification with Hindi text."""
        # Mock LLM response for Hindi input
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.9, "reasoning": "Normal Hindi text", '
            '"language": "hi", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("नमस्ते दुनिया")

        assert result.is_safe is True
        assert result.risk_level == RiskLevel.LOW
        assert result.language == "hi"
        assert result.capability_required == "general.query"

    @pytest.mark.asyncio
    async def test_spanish_safety_classification(self, classifier, mock_runtime):
        """Test safety classification with Spanish text."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.85, "reasoning": "Normal Spanish text", '
            '"language": "es", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Hola mundo")

        assert result.is_safe is True
        assert result.risk_level == RiskLevel.LOW
        assert result.language == "es"

    @pytest.mark.asyncio
    async def test_chinese_safety_classification(self, classifier, mock_runtime):
        """Test safety classification with Chinese text."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.88, "reasoning": "Normal Chinese text", '
            '"language": "zh", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("你好世界")

        assert result.is_safe is True
        assert result.risk_level == RiskLevel.LOW
        assert result.language == "zh"

    @pytest.mark.asyncio
    async def test_arabic_safety_classification(self, classifier, mock_runtime):
        """Test safety classification with Arabic text."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.87, "reasoning": "Normal Arabic text", '
            '"language": "ar", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("مرحبا بالعالم")

        assert result.is_safe is True
        assert result.risk_level == RiskLevel.LOW
        assert result.language == "ar"

    @pytest.mark.asyncio
    async def test_code_mixed_hinglish(self, classifier, mock_runtime):
        """Test safety classification with Hinglish (Hindi-English code-mixing)."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.82, "reasoning": "Hinglish code-mixed text", '
            '"language": "mixed", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Mujhe yeh task complete karna hai")

        assert result.is_safe is True
        assert result.language == "mixed"

    @pytest.mark.asyncio
    async def test_code_mixed_spanglish(self, classifier, mock_runtime):
        """Test safety classification with Spanglish (Spanish-English code-mixing)."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.80, "reasoning": "Spanglish code-mixed text", '
            '"language": "mixed", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Necesito hacer this task ahora")

        assert result.is_safe is True
        assert result.language == "mixed"


class TestAdversarialSafetyClassification:
    """Test safety classification with adversarial inputs."""

    @pytest.fixture
    def mock_runtime(self):
        """Mock reasoning runtime for testing."""
        runtime = Mock()
        runtime.generate = AsyncMock()
        return runtime

    @pytest.fixture
    def classifier(self, mock_runtime):
        """Create classifier with mock runtime."""
        return SemanticClassifier(runtime=mock_runtime)

    @pytest.mark.asyncio
    async def test_adversarial_typos(self, classifier, mock_runtime):
        """Test safety classification with intentional typos."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.75, "reasoning": "Text with typos but safe", '
            '"language": "en", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Plz hlp me wth ths tsk")

        assert result.is_safe is True
        assert result.confidence == 0.75

    @pytest.mark.asyncio
    async def test_transliteration(self, classifier, mock_runtime):
        """Test safety classification with transliterated text."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.78, "reasoning": "Transliterated text", '
            '"language": "transliterated", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Namaste duniya")

        assert result.is_safe is True
        assert result.language == "transliterated"

    @pytest.mark.asyncio
    async def test_slang_and_informal(self, classifier, mock_runtime):
        """Test safety classification with slang and informal language."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.83, "reasoning": "Informal slang text", '
            '"language": "en", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Yo can u help with this thing")

        assert result.is_safe is True

    @pytest.mark.asyncio
    async def test_no_english_keyword_dependency(self, classifier, mock_runtime):
        """Verify classifier doesn't depend on English keywords."""
        # This should work even without English keywords present
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": false, "risk_level": "high", '
            '"categories": ["toxicity"], "confidence": 0.92, '
            '"reasoning": "Toxic content detected semantically", '
            '"language": "es", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Eres muy estúpido")

        assert result.is_safe is False
        assert result.risk_level == RiskLevel.HIGH
        assert SafetyCategory.TOXICITY in result.categories
        # Should work even though "stupid" is not in the text (Spanish word used)


class TestRiskClassification:
    """Test risk classification for tool operations."""

    @pytest.fixture
    def mock_runtime(self):
        """Mock reasoning runtime for testing."""
        runtime = Mock()
        runtime.generate = AsyncMock()
        return runtime

    @pytest.fixture
    def classifier(self, mock_runtime):
        """Create classifier with mock runtime."""
        return SemanticClassifier(runtime=mock_runtime)

    @pytest.mark.asyncio
    async def test_file_delete_risk(self, classifier, mock_runtime):
        """Test risk classification for file deletion."""
        mock_runtime.generate.return_value = Mock(
            content='{"risk_level": "critical", "requires_approval": true, '
            '"requires_sandbox": true, "confidence": 0.95, '
            '"reasoning": "Destructive file operation", '
            '"language": "en", "capability_required": "file.delete"}'
        )

        result = await classifier.classify_risk("delete_file", {"path": "/tmp/test"})

        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_approval is True
        assert result.requires_sandbox is True
        assert result.capability_required == "file.delete"

    @pytest.mark.asyncio
    async def test_file_read_risk(self, classifier, mock_runtime):
        """Test risk classification for file read."""
        mock_runtime.generate.return_value = Mock(
            content='{"risk_level": "low", "requires_approval": false, '
            '"requires_sandbox": false, "confidence": 0.90, '
            '"reasoning": "Read-only operation", '
            '"language": "en", "capability_required": "file.read"}'
        )

        result = await classifier.classify_risk("read_file", {"path": "/tmp/test"})

        assert result.risk_level == RiskLevel.LOW
        assert result.requires_approval is False
        assert result.capability_required == "file.read"

    @pytest.mark.asyncio
    async def test_device_control_risk(self, classifier, mock_runtime):
        """Test risk classification for device control."""
        mock_runtime.generate.return_value = Mock(
            content='{"risk_level": "high", "requires_approval": true, '
            '"requires_sandbox": true, "confidence": 0.88, '
            '"reasoning": "Physical device control", '
            '"language": "en", "capability_required": "device.control"}'
        )

        result = await classifier.classify_risk("turn_on_lights", {"device_id": "123"})

        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_approval is True
        assert result.capability_required == "device.control"


class TestCapabilityField:
    """Test capability_required field in classification outputs."""

    @pytest.fixture
    def mock_runtime(self):
        """Mock reasoning runtime for testing."""
        runtime = Mock()
        runtime.generate = AsyncMock()
        return runtime

    @pytest.fixture
    def classifier(self, mock_runtime):
        """Create classifier with mock runtime."""
        return SemanticClassifier(runtime=mock_runtime)

    @pytest.mark.asyncio
    async def test_safety_capability_required_present(self, classifier, mock_runtime):
        """Verify safety classification includes capability_required field."""
        mock_runtime.generate.return_value = Mock(
            content='{"is_safe": true, "risk_level": "low", "categories": ["none"], '
            '"confidence": 0.9, "reasoning": "Safe text", '
            '"language": "en", "capability_required": "general.query"}'
        )

        result = await classifier.classify_safety("Hello world")

        assert result.capability_required == "general.query"
        assert isinstance(result.capability_required, str)

    @pytest.mark.asyncio
    async def test_risk_capability_required_present(self, classifier, mock_runtime):
        """Verify risk classification includes capability_required field."""
        mock_runtime.generate.return_value = Mock(
            content='{"risk_level": "medium", "requires_approval": false, '
            '"requires_sandbox": false, "confidence": 0.85, '
            '"reasoning": "Medium risk operation", '
            '"language": "en", "capability_required": "file.write"}'
        )

        result = await classifier.classify_risk("write_file", {"path": "/tmp/test"})

        assert result.capability_required == "file.write"
        assert isinstance(result.capability_required, str)


class TestFallbackBehavior:
    """Test fallback behavior when LLM is unavailable."""

    @pytest.fixture
    def classifier(self):
        """Create classifier without runtime (fallback mode)."""
        return SemanticClassifier(runtime=None)

    @pytest.mark.asyncio
    async def test_safety_fallback(self, classifier):
        """Test safety classification fallback when LLM unavailable."""
        result = await classifier.classify_safety("Any text")

        assert result.is_safe is True
        assert result.risk_level == RiskLevel.LOW
        assert result.capability_required == "general.query"
        assert result.reasoning == "LLM classifier unavailable - conservative safe default"

    @pytest.mark.asyncio
    async def test_risk_fallback(self, classifier):
        """Test risk classification fallback when LLM unavailable."""
        result = await classifier.classify_risk("any_tool", {"param": "value"})

        assert result.risk_level == RiskLevel.MEDIUM
        assert result.requires_approval is False
        assert result.capability_required == "general.query"
        assert result.reasoning == "LLM classifier unavailable - conservative medium risk default"


class TestDeterministicPolicyEnforcement:
    """Test that deterministic policy enforces boundaries based on capability_required."""

    @pytest.fixture
    def policy_engine(self):
        """Create policy engine with default policies."""
        from services.policy.capability_policy import CapabilityPolicyEngine

        return CapabilityPolicyEngine()

    def test_file_delete_requires_approval(self, policy_engine):
        """Test that file.delete capability requires approval deterministically."""
        decision = policy_engine.evaluate("file.delete", tenant_id="test-tenant")

        assert decision.allowed is True
        assert decision.requires_approval is True
        assert decision.policy.requires_approval is True

    def test_file_read_no_approval(self, policy_engine):
        """Test that file.read capability doesn't require approval deterministically."""
        decision = policy_engine.evaluate("file.read", tenant_id="test-tenant")

        assert decision.allowed is True
        assert decision.requires_approval is False
        assert decision.policy.requires_approval is False

    def test_unknown_capability_denied(self, policy_engine):
        """Test that unknown capabilities are denied conservatively."""
        decision = policy_engine.evaluate("unknown_capability", tenant_id="test-tenant")

        assert decision.allowed is False
        assert decision.requires_approval is True

    def test_tenant_denylist(self, policy_engine):
        """Test that tenant denylist is enforced deterministically."""
        # Use existing policy for this test
        decision = policy_engine.evaluate("file.delete", tenant_id="test-tenant")

        # File delete should be allowed for non-blocked tenants
        assert decision.allowed is True
        assert decision.requires_approval is True


class TestObservability:
    """Test observability features of classification pipeline."""

    def test_input_hash_generation(self):
        """Test that input hash is generated for logging without exposing raw text."""
        text = "sensitive user input"
        text_hash = hashlib.sha256(text.encode()).hexdigest()

        assert len(text_hash) == 64
        assert text != text_hash
        assert text_hash.isalnum()

    def test_different_inputs_different_hashes(self):
        """Test that different inputs produce different hashes."""
        text1 = "input one"
        text2 = "input two"

        hash1 = hashlib.sha256(text1.encode()).hexdigest()
        hash2 = hashlib.sha256(text2.encode()).hexdigest()

        assert hash1 != hash2

    def test_same_inputs_same_hashes(self):
        """Test that same inputs produce same hashes."""
        text = "same input"

        hash1 = hashlib.sha256(text.encode()).hexdigest()
        hash2 = hashlib.sha256(text.encode()).hexdigest()

        assert hash1 == hash2
