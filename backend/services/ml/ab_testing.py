"""
A/B Testing - A/B Testing for Models

Implements A/B testing framework for ML models.
Supports experiment management, traffic splitting, and statistical analysis.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ExperimentStatus(StrEnum):
    """Experiment status."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class Variant:
    """Model variant."""

    variant_id: str
    model_id: str
    traffic_percentage: int
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class Experiment:
    """A/B test experiment."""

    experiment_id: str
    experiment_name: str
    variants: list[Variant]
    status: ExperimentStatus
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    winning_variant: str | None


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Experiment result."""

    result_id: str
    experiment_id: str
    variant_id: str
    metric_name: str
    metric_value: float
    sample_size: int
    recorded_at: datetime


class ABTesting:
    """
    A/B testing framework for models.

    Features:
    - Experiment management
    - Traffic splitting
    - Statistical analysis
    - Variant comparison
    """

    def __init__(self) -> None:
        """Initialize A/B testing."""
        self._experiments: dict[str, Experiment] = {}
        self._results: dict[str, list[ExperimentResult]] = {}  # experiment_id -> results
        self._inference_callback: Callable[[str, Any], Awaitable[Any]] | None = None

    def set_inference_callback(
        self,
        callback: Callable[[str, Any], Awaitable[Any]],
    ) -> None:
        """
        Set inference callback for variants.

        Args:
            callback: Async function to run inference on variant
        """
        self._inference_callback = callback

    def create_experiment(
        self,
        experiment_id: str,
        experiment_name: str,
        variants: list[Variant],
    ) -> Experiment:
        """
        Create an A/B test experiment.

        Args:
            experiment_id: Experiment identifier
            experiment_name: Experiment name
            variants: Model variants

        Returns:
            Experiment
        """
        experiment = Experiment(
            experiment_id=experiment_id,
            experiment_name=experiment_name,
            variants=variants,
            status=ExperimentStatus.DRAFT,
            created_at=datetime.now(UTC),
            started_at=None,
            ended_at=None,
            winning_variant=None,
        )

        self._experiments[experiment_id] = experiment
        self._results[experiment_id] = []

        logger.info(
            "experiment_created",
            experiment_id=experiment_id,
            experiment_name=experiment_name,
            variant_count=len(variants),
        )

        return experiment

    async def start_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Start an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Updated experiment
        """
        experiment = self._experiments.get(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        updated_experiment = Experiment(
            experiment_id=experiment.experiment_id,
            experiment_name=experiment.experiment_name,
            variants=experiment.variants,
            status=ExperimentStatus.RUNNING,
            created_at=experiment.created_at,
            started_at=datetime.now(UTC),
            ended_at=None,
            winning_variant=None,
        )

        self._experiments[experiment_id] = updated_experiment

        logger.info(
            "experiment_started",
            experiment_id=experiment_id,
        )

        return updated_experiment

    async def get_variant_for_request(
        self,
        experiment_id: str,
    ) -> str | None:
        """
        Get variant for a request based on traffic split.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Variant ID or None
        """
        experiment = self._experiments.get(experiment_id)

        if not experiment or experiment.status != ExperimentStatus.RUNNING:
            return None

        # Simple traffic split based on hash of request ID
        # In production, use more sophisticated traffic splitting
        import random

        rand = random.random() * 100
        cumulative = 0

        for variant in experiment.variants:
            cumulative += variant.traffic_percentage
            if rand <= cumulative:
                return variant.variant_id

        return None

    async def record_result(
        self,
        experiment_id: str,
        variant_id: str,
        metric_name: str,
        metric_value: float,
        sample_size: int = 1,
    ) -> ExperimentResult:
        """
        Record experiment result.

        Args:
            experiment_id: Experiment identifier
            variant_id: Variant identifier
            metric_name: Metric name
            metric_value: Metric value
            sample_size: Sample size

        Returns:
            Experiment result
        """
        result_id = f"res-{datetime.now(UTC).timestamp()}"

        result = ExperimentResult(
            result_id=result_id,
            experiment_id=experiment_id,
            variant_id=variant_id,
            metric_name=metric_name,
            metric_value=metric_value,
            sample_size=sample_size,
            recorded_at=datetime.now(UTC),
        )

        if experiment_id in self._results:
            self._results[experiment_id].append(result)

        logger.debug(
            "result_recorded",
            result_id=result_id,
            experiment_id=experiment_id,
            variant_id=variant_id,
            metric_name=metric_name,
        )

        return result

    async def stop_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Stop an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Updated experiment
        """
        experiment = self._experiments.get(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Determine winning variant
        winning_variant = self._determine_winning_variant(experiment_id)

        updated_experiment = Experiment(
            experiment_id=experiment.experiment_id,
            experiment_name=experiment.experiment_name,
            variants=experiment.variants,
            status=ExperimentStatus.STOPPED,
            created_at=experiment.created_at,
            started_at=experiment.started_at,
            ended_at=datetime.now(UTC),
            winning_variant=winning_variant,
        )

        self._experiments[experiment_id] = updated_experiment

        logger.info(
            "experiment_stopped",
            experiment_id=experiment_id,
            winning_variant=winning_variant,
        )

        return updated_experiment

    def _determine_winning_variant(
        self,
        experiment_id: str,
    ) -> str | None:
        """
        Determine winning variant based on metrics.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Winning variant ID or None
        """
        results = self._results.get(experiment_id, [])

        if not results:
            return None

        # Aggregate metrics by variant
        variant_metrics: dict[str, dict[str, list[float]]] = {}

        for result in results:
            if result.variant_id not in variant_metrics:
                variant_metrics[result.variant_id] = {}

            if result.metric_name not in variant_metrics[result.variant_id]:
                variant_metrics[result.variant_id][result.metric_name] = []

            variant_metrics[result.variant_id][result.metric_name].append(result.metric_value)

        # Calculate averages
        variant_averages: dict[str, float] = {}

        for variant_id, metrics in variant_metrics.items():
            # Use first metric for comparison
            metric_name = list(metrics.keys())[0]
            values = metrics[metric_name]

            if values:
                variant_averages[variant_id] = sum(values) / len(values)

        # Return variant with highest average
        if variant_averages:
            return max(variant_averages.items(), key=lambda x: x[1])[0]

        return None

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """
        Get an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Experiment or None
        """
        return self._experiments.get(experiment_id)

    def get_experiments(
        self,
        status: ExperimentStatus | None = None,
    ) -> list[Experiment]:
        """
        Get all experiments.

        Args:
            status: Filter by status

        Returns:
            List of experiments
        """
        experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        return sorted(experiments, key=lambda e: e.created_at, reverse=True)

    def get_results(
        self,
        experiment_id: str,
        variant_id: str | None = None,
        metric_name: str | None = None,
    ) -> list[ExperimentResult]:
        """
        Get experiment results.

        Args:
            experiment_id: Experiment identifier
            variant_id: Filter by variant
            metric_name: Filter by metric

        Returns:
            List of experiment results
        """
        results = self._results.get(experiment_id, [])

        if variant_id:
            results = [r for r in results if r.variant_id == variant_id]

        if metric_name:
            results = [r for r in results if r.metric_name == metric_name]

        return sorted(results, key=lambda r: r.recorded_at, reverse=True)

    def get_ab_stats(self) -> dict[str, Any]:
        """
        Get A/B testing statistics.

        Returns:
            A/B testing statistics
        """
        total_experiments = len(self._experiments)
        running_experiments = sum(
            1 for e in self._experiments.values() if e.status == ExperimentStatus.RUNNING
        )
        completed_experiments = sum(
            1 for e in self._experiments.values() if e.status == ExperimentStatus.COMPLETED
        )

        total_results = sum(len(results) for results in self._results.values())

        return {
            "total_experiments": total_experiments,
            "running_experiments": running_experiments,
            "completed_experiments": completed_experiments,
            "total_results": total_results,
        }
