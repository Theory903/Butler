"""Tests for ML Provider Health Tracker and health-gated routing."""

import time

import pytest

from domain.ml.contracts import ReasoningTier
from domain.ml.runtime_health import HealthStatus
from services.ml.provider_health import MLProviderHealthTracker


class TestMLProviderHealthTracker:
    """Test MLProviderHealthTracker functionality."""

    def test_initial_state_unknown(self):
        """New providers start with UNKNOWN status before enough samples."""
        tracker = MLProviderHealthTracker(min_samples=5)
        health = tracker.get_provider_health("anthropic")
        
        assert health.provider_name == "anthropic"
        assert health.status == HealthStatus.UNKNOWN
        assert health.error_rate == 0.0
        assert health.latency_ms is None

    def test_record_success_increments_metrics(self):
        """Recording success increments success count and total requests."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_success("anthropic", latency_ms=150.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.status == HealthStatus.HEALTHY
        assert health.error_rate == 0.0
        assert health.latency_ms == 125.0  # Average of 100 and 150

    def test_record_failure_increments_error_rate(self):
        """Recording failure increments error rate."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_failure("anthropic", latency_ms=50.0)
        tracker.record_model_failure("anthropic", latency_ms=60.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.error_rate == 2.0 / 3.0
        assert health.status == HealthStatus.UNHEALTHY  # Above default 0.5 threshold

    def test_high_latency_marks_degraded(self):
        """High latency marks provider as DEGRADED."""
        tracker = MLProviderHealthTracker(
            min_samples=1,
            latency_threshold_ms=1000.0,
        )
        
        tracker.record_model_success("anthropic", latency_ms=2000.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.status == HealthStatus.DEGRADED
        assert health.latency_ms == 2000.0

    def test_cooldown_period_after_failure(self):
        """Provider stays UNHEALTHY during cooldown after recent failure."""
        tracker = MLProviderHealthTracker(
            min_samples=1,
            cooldown_seconds=60.0,
        )
        
        # Record a failure
        tracker.record_model_failure("anthropic", latency_ms=50.0)
        
        # Immediately record success - should still be unhealthy due to cooldown
        tracker.record_model_success("anthropic", latency_ms=100.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.status == HealthStatus.UNHEALTHY

    def test_cooldown_expires_after_time(self):
        """Provider can recover after cooldown period expires."""
        tracker = MLProviderHealthTracker(
            min_samples=1,
            cooldown_seconds=0.1,  # Very short cooldown for testing
        )
        
        # Record a failure
        tracker.record_model_failure("anthropic", latency_ms=50.0)
        
        # Wait for cooldown to expire
        time.sleep(0.15)
        
        # Record success
        tracker.record_model_success("anthropic", latency_ms=100.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.status == HealthStatus.HEALTHY

    def test_is_available_healthy(self):
        """Healthy providers are available."""
        tracker = MLProviderHealthTracker(min_samples=1)
        tracker.record_model_success("anthropic", latency_ms=100.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.is_available() is True
        assert health.is_preferred() is True

    def test_is_available_degraded(self):
        """Degraded providers are available but not preferred."""
        tracker = MLProviderHealthTracker(
            min_samples=1,
            latency_threshold_ms=1000.0,
        )
        tracker.record_model_success("anthropic", latency_ms=2000.0)
        
        health = tracker.get_provider_health("anthropic")
        assert health.is_available() is True
        assert health.is_preferred() is False

    def test_is_available_unhealthy(self):
        """Unhealthy providers are not available."""
        tracker = MLProviderHealthTracker(
            min_samples=1,
            error_threshold=0.5,
        )
        tracker.record_model_failure("anthropic")
        tracker.record_model_failure("anthropic")
        
        health = tracker.get_provider_health("anthropic")
        assert health.is_available() is False
        assert health.is_preferred() is False

    def test_reset_provider_clears_metrics(self):
        """Resetting a provider clears its metrics."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_failure("anthropic")
        
        tracker.reset_provider("anthropic")
        
        health = tracker.get_provider_health("anthropic")
        assert health.status == HealthStatus.UNKNOWN
        assert health.error_rate == 0.0
        assert health.latency_ms is None

    def test_multiple_providers_tracked_separately(self):
        """Multiple providers are tracked independently."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_failure("openai")
        
        anthropic_health = tracker.get_provider_health("anthropic")
        openai_health = tracker.get_provider_health("openai")
        
        assert anthropic_health.status == HealthStatus.HEALTHY
        assert openai_health.status == HealthStatus.UNHEALTHY

    def test_get_metrics_summary(self):
        """Metrics summary provides comprehensive provider data."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_failure("anthropic", latency_ms=50.0)
        
        summary = tracker.get_metrics_summary()
        
        assert "anthropic" in summary
        assert summary["anthropic"]["total_requests"] == 2
        assert summary["anthropic"]["successful_requests"] == 1
        assert summary["anthropic"]["failed_requests"] == 1
        assert summary["anthropic"]["error_rate"] == 0.5
        assert summary["anthropic"]["average_latency_ms"] == 75.0

    def test_get_all_provider_health(self):
        """Get health for all tracked providers."""
        tracker = MLProviderHealthTracker(min_samples=1)
        
        tracker.record_model_success("anthropic", latency_ms=100.0)
        tracker.record_model_success("openai", latency_ms=150.0)
        
        all_health = tracker.get_all_provider_health()
        
        assert len(all_health) == 2
        assert "anthropic" in [h.provider_name for h in all_health.values()]
        assert "openai" in [h.provider_name for h in all_health.values()]


class TestHealthGatedRouting:
    """Test health-gated routing integration with MLRuntimeManager."""

    def test_filter_by_health_removes_unhealthy(self):
        """_filter_by_health removes unhealthy providers from candidates."""
        from services.ml.runtime import MLRuntimeManager, RuntimeCandidate
        
        tracker = MLProviderHealthTracker(min_samples=1)
        runtime = MLRuntimeManager(registry=None, breakers=None, health_tracker=tracker)
        
        # Mark anthropic as unhealthy
        tracker.record_model_failure("anthropic")
        tracker.record_model_failure("anthropic")
        
        # Mark openai as healthy
        tracker.record_model_success("openai", latency_ms=100.0)
        
        candidates = [
            RuntimeCandidate(
                name="cloud-anthropic",
                provider_name="anthropic",
                model_version="claude-3",
                tier=ReasoningTier.T3,
            ),
            RuntimeCandidate(
                name="cloud-openai",
                provider_name="openai",
                model_version="gpt-4",
                tier=ReasoningTier.T3,
            ),
        ]
        
        filtered = runtime._filter_by_health(candidates)
        
        assert len(filtered) == 1
        assert filtered[0].provider_name == "openai"

    def test_filter_by_health_keeps_degraded(self):
        """_filter_by_health keeps degraded providers (they're available)."""
        from services.ml.runtime import MLRuntimeManager, RuntimeCandidate
        from domain.ml.runtime_health import HealthStatus
        
        tracker = MLProviderHealthTracker(
            min_samples=1,
            latency_threshold_ms=1000.0,
        )
        runtime = MLRuntimeManager(registry=None, breakers=None, health_tracker=tracker)
        
        # Mark anthropic as degraded (high latency)
        tracker.record_model_success("anthropic", latency_ms=2000.0)
        
        candidates = [
            RuntimeCandidate(
                name="cloud-anthropic",
                provider_name="anthropic",
                model_version="claude-3",
                tier=ReasoningTier.T3,
            ),
        ]
        
        filtered = runtime._filter_by_health(candidates)
        
        assert len(filtered) == 1
        assert filtered[0].provider_name == "anthropic"

    def test_filter_by_health_no_tracker(self):
        """Without health tracker, all candidates pass through."""
        from services.ml.runtime import MLRuntimeManager, RuntimeCandidate
        
        runtime = MLRuntimeManager(registry=None, breakers=None, health_tracker=None)
        
        candidates = [
            RuntimeCandidate(
                name="cloud-anthropic",
                provider_name="anthropic",
                model_version="claude-3",
                tier=ReasoningTier.T3,
            ),
        ]
        
        filtered = runtime._filter_by_health(candidates)
        
        assert len(filtered) == 1
