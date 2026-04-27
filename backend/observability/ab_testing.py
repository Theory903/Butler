"""AB Testing Framework.

Phase I: AB testing using statistical analysis.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Variant:
    """An AB test variant."""

    variant_id: str
    name: str
    weight: float = 0.5
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class Experiment:
    """An AB test experiment."""

    experiment_id: str
    name: str
    variants: list[Variant] = field(default_factory=list)
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """An observation from AB testing."""

    observation_id: str
    experiment_id: str
    variant_id: str
    user_id: str
    metric_name: str
    value: float
    timestamp: float


class ButlerABTesting:
    """AB testing framework for Butler.

    This class:
    - Manages AB test experiments
    - Tracks observations
    - Provides statistical analysis
    - Supports feature flagging
    """

    def __init__(self):
        """Initialize AB testing framework."""
        self._experiments: dict[str, Experiment] = {}
        self._observations: dict[str, Observation] = {}

    def create_experiment(self, name: str, variants: list[Variant]) -> Experiment:
        """Create an AB test experiment.

        Args:
            name: Experiment name
            variants: List of variants

        Returns:
            Created experiment
        """
        experiment_id = str(uuid.uuid4())
        experiment = Experiment(experiment_id=experiment_id, name=name, variants=variants)
        self._experiments[experiment_id] = experiment
        logger.info("experiment_created", experiment_id=experiment_id, name=name)
        return experiment

    def get_variant(self, experiment_id: str, user_id: str) -> Variant | None:
        """Get variant for a user in an experiment.

        Args:
            experiment_id: Experiment identifier
            user_id: User identifier

        Returns:
            Assigned variant or None
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment or not experiment.is_active:
            return None

        # Simple hash-based assignment
        import hashlib

        hash_value = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        total_weight = sum(v.weight for v in experiment.variants)
        normalized = (hash_value % 1000) / 1000

        cumulative = 0.0
        for variant in experiment.variants:
            cumulative += variant.weight / total_weight
            if normalized < cumulative:
                return variant

        return experiment.variants[-1]

    def record_observation(
        self,
        experiment_id: str,
        variant_id: str,
        user_id: str,
        metric_name: str,
        value: float,
    ) -> Observation:
        """Record an observation.

        Args:
            experiment_id: Experiment identifier
            variant_id: Variant identifier
            user_id: User identifier
            metric_name: Metric name
            value: Metric value

        Returns:
            Recorded observation
        """
        import time

        observation_id = str(uuid.uuid4())
        observation = Observation(
            observation_id=observation_id,
            experiment_id=experiment_id,
            variant_id=variant_id,
            user_id=user_id,
            metric_name=metric_name,
            value=value,
            timestamp=time.time(),
        )
        self._observations[observation_id] = observation
        return observation

    def get_experiment_results(self, experiment_id: str) -> dict[str, Any]:
        """Get experiment results with statistical analysis.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Experiment results
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {}

        observations = [o for o in self._observations.values() if o.experiment_id == experiment_id]

        # Group by variant
        variant_metrics: dict[str, list[float]] = {}
        for variant in experiment.variants:
            variant_metrics[variant.variant_id] = []

        for obs in observations:
            if obs.variant_id in variant_metrics:
                variant_metrics[obs.variant_id].append(obs.value)

        # Calculate statistics
        results = {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "variants": [],
        }

        for variant in experiment.variants:
            values = variant_metrics.get(variant.variant_id, [])
            if values:
                import statistics

                results["variants"].append(
                    {
                        "variant_id": variant.variant_id,
                        "name": variant.name,
                        "count": len(values),
                        "mean": statistics.mean(values),
                        "median": statistics.median(values),
                        "stddev": statistics.stdev(values) if len(values) > 1 else 0,
                    }
                )
            else:
                results["variants"].append(
                    {
                        "variant_id": variant.variant_id,
                        "name": variant.name,
                        "count": 0,
                        "mean": 0,
                        "median": 0,
                        "stddev": 0,
                    }
                )

        return results

    def activate_experiment(self, experiment_id: str) -> None:
        """Activate an experiment.

        Args:
            experiment_id: Experiment identifier
        """
        experiment = self._experiments.get(experiment_id)
        if experiment:
            experiment.is_active = True
            logger.info("experiment_activated", experiment_id=experiment_id)

    def deactivate_experiment(self, experiment_id: str) -> None:
        """Deactivate an experiment.

        Args:
            experiment_id: Experiment identifier
        """
        experiment = self._experiments.get(experiment_id)
        if experiment:
            experiment.is_active = False
            logger.info("experiment_deactivated", experiment_id=experiment_id)
