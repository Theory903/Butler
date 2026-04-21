"""
Tests for Butler Model Improvement Pipeline
SWE-5 Grade Test Coverage
"""

from datetime import datetime, timedelta
import pytest
from services.ml.training_pipeline import (
    ConsentModel, ConsentLevel, DataCategory, TrainingCandidate,
    TrainingCandidateStatus, Anonymizer, PoisoningGuard, OfflineTrainer,
    CircuitBreaker, TrainingPipeline
)


class TestConsentModel:
    def test_consent_level_ordering(self):
        """Test consent level permission hierarchy."""
        never = ConsentModel(user_id="test", consent_level=ConsentLevel.NEVER_TRAIN)
        eval_only = ConsentModel(user_id="test", consent_level=ConsentLevel.PRIVATE_EVAL_ONLY)
        opt_in = ConsentModel(user_id="test", consent_level=ConsentLevel.OPT_IN_TRAINING)

        assert not never.allows_training()
        assert not never.allows_evaluation()

        assert not eval_only.allows_training()
        assert eval_only.allows_evaluation()

        assert opt_in.allows_training()
        assert opt_in.allows_evaluation()

    def test_consent_expiry_validation(self):
        """Test that past expiry dates are rejected."""
        with pytest.raises(ValueError):
            ConsentModel(
                user_id="test",
                consent_level=ConsentLevel.OPT_IN_TRAINING,
                expires_at=datetime.utcnow() - timedelta(hours=1)
            )

    def test_audit_trail_immutability(self):
        """Test that audit trail is immutable and correctly appended."""
        consent = ConsentModel(user_id="test", consent_level=ConsentLevel.OPT_IN_TRAINING)
        updated = consent.with_audit_entry("grant", "user", "explicit opt-in")

        assert len(consent.audit_trail) == 0
        assert len(updated.audit_trail) == 1
        assert updated.audit_trail[0]["action"] == "grant"


class TestAnonymizer:
    def test_pii_removal(self):
        """Test PII patterns are correctly anonymized."""
        anonymizer = Anonymizer()

        test_cases = [
            ("Contact me at test@example.com", "Contact me at [EMAIL]"),
            ("Call 555-123-4567 for help", "Call [PHONE] for help"),
            ("IP is 192.168.1.1", "IP is [IP_ADDRESS]"),
        ]

        for input_text, expected in test_cases:
            assert anonymizer.anonymize_text(input_text) == expected

    def test_identifier_hashing(self):
        """Test identifiers are irreversibly hashed."""
        anonymizer = Anonymizer()
        hash1 = anonymizer.hash_identifier("user-123")
        hash2 = anonymizer.hash_identifier("user-123")

        assert hash1 == hash2
        assert "user-123" not in hash1

    def test_differential_noise(self):
        """Test differential privacy noise is added correctly."""
        anonymizer = Anonymizer(epsilon=10.0)
        values = [anonymizer.add_differential_noise(5.0) for _ in range(100)]

        # Mean should be approximately 5.0 with high epsilon
        mean = sum(values) / len(values)
        assert abs(mean - 5.0) < 0.5


class TestCircuitBreaker:
    def test_circuit_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(2):
            cb = cb.record_failure()
            assert not cb.open

        cb = cb.record_failure()
        assert cb.open

    def test_circuit_allows_after_recovery(self):
        """Test circuit allows requests after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1)
        cb = cb.record_failure()
        assert cb.open

        import time
        time.sleep(1.1)
        assert cb.allow_request()


class TestPoisoningGuard:
    def test_poisoning_scoring(self):
        """Test poisoning guard returns valid score range."""
        guard = PoisoningGuard()
        candidate = TrainingCandidate(
            user_id="test",
            memory_id="mem-123",
            raw_content="test content",
            consent_level=ConsentLevel.OPT_IN_TRAINING,
            data_category=DataCategory.PUBLIC
        )

        is_safe, score = guard.scan_candidate(candidate)
        assert 0.0 <= score <= 1.0
        assert isinstance(is_safe, bool)


class TestOfflineTrainer:
    def test_watermark_generation(self):
        """Test training watermarks are unique and consistent."""
        trainer = OfflineTrainer()
        watermark1 = trainer.generate_watermark("candidate-1")
        watermark2 = trainer.generate_watermark("candidate-1")
        watermark3 = trainer.generate_watermark("candidate-2")

        assert watermark1 == watermark2
        assert watermark1 != watermark3
        assert len(watermark1) == 16


class TestTrainingPipeline:
    @pytest.fixture
    def mock_consent_store(self):
        class MockStore:
            def get_consent(self, user_id):
                return ConsentModel(user_id=user_id, consent_level=ConsentLevel.OPT_IN_TRAINING)
        return MockStore()

    def test_pipeline_initialization(self, mock_consent_store):
        """Test pipeline initializes correctly with all components."""
        pipeline = TrainingPipeline(consent_store=mock_consent_store)
        assert pipeline.anonymizer is not None
        assert pipeline.extractor is not None
        assert pipeline.labeler is not None
        assert pipeline.poisoning_guard is not None
        assert pipeline.trainer is not None
