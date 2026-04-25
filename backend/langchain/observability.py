"""Butler Observability for LangChain Agents.

Provides tracing, metrics, and evaluation capabilities.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentSpan:
    """A span representing an agent operation."""

    span_id: str
    parent_span_id: str | None = None
    operation_name: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    duration_ms: float = 0.0
    status: str = "started"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self, status: str = "completed") -> None:
        """Finish the span."""
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes or {},
        })


@dataclass
class AgentMetric:
    """A metric measurement."""

    name: str
    value: float
    unit: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ButlerAgentTracer:
    """Tracer for agent operations.

    This tracer:
    - Creates and manages spans
    - Tracks operation timing
    - Records events and attributes
    - Supports distributed tracing
    """

    def __init__(self, service_name: str = "butler-langchain"):
        """Initialize the tracer.

        Args:
            service_name: Service name for tracing
        """
        self._service_name = service_name
        self._active_spans: dict[str, AgentSpan] = {}
        self._completed_spans: list[AgentSpan] = []

    def start_span(
        self,
        operation_name: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> AgentSpan:
        """Start a new span.

        Args:
            operation_name: Name of the operation
            parent_span_id: Optional parent span ID
            attributes: Optional span attributes

        Returns:
            The new span
        """
        import uuid
        span_id = str(uuid.uuid4())

        span = AgentSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            attributes=attributes or {},
        )

        self._active_spans[span_id] = span
        logger.info("tracer_span_started", span_id=span_id, operation=operation_name)
        return span

    def finish_span(self, span_id: str, status: str = "completed") -> None:
        """Finish a span.

        Args:
            span_id: Span ID
            status: Span status
        """
        span = self._active_spans.get(span_id)
        if span:
            span.finish(status)
            self._completed_spans.append(span)
            del self._active_spans[span_id]
            logger.info("tracer_span_finished", span_id=span_id, status=status)

    def get_span(self, span_id: str) -> AgentSpan | None:
        """Get a span by ID.

        Args:
            span_id: Span ID

        Returns:
            Span or None
        """
        return self._active_spans.get(span_id)

    def get_active_spans(self) -> list[AgentSpan]:
        """Get all active spans.

        Returns:
            List of active spans
        """
        return list(self._active_spans.values())

    def get_completed_spans(self) -> list[AgentSpan]:
        """Get all completed spans.

        Returns:
            List of completed spans
        """
        return self._completed_spans.copy()

    def clear_completed_spans(self) -> None:
        """Clear completed spans."""
        self._completed_spans.clear()
        logger.info("tracer_completed_spans_cleared")


class ButlerAgentMetrics:
    """Metrics collector for agent operations.

    This collector:
    - Records metric measurements
    - Aggregates metrics over time
    - Supports histogram and counter metrics
    - Provides metric querying
    """

    def __init__(self):
        """Initialize the metrics collector."""
        self._metrics: list[AgentMetric] = []
        self._counters: dict[str, float] = {}

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a metric.

        Args:
            name: Metric name
            value: Metric value
            unit: Metric unit
            labels: Optional metric labels
        """
        metric = AgentMetric(
            name=name,
            value=value,
            unit=unit,
            labels=labels or {},
        )
        self._metrics.append(metric)

        # Update counter
        if name not in self._counters:
            self._counters[name] = 0.0
        self._counters[name] += value

        logger.debug("metric_recorded", name=name, value=value)

    def increment_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric.

        Args:
            name: Counter name
            value: Value to increment by
            labels: Optional labels
        """
        self.record_metric(name, value, "count", labels)

    def record_timing(self, name: str, duration_ms: float, labels: dict[str, str] | None = None) -> None:
        """Record a timing metric.

        Args:
            name: Timing name
            duration_ms: Duration in milliseconds
            labels: Optional labels
        """
        self.record_metric(name, duration_ms, "ms", labels)

    def get_metric(self, name: str) -> list[AgentMetric]:
        """Get all metrics with a name.

        Args:
            name: Metric name

        Returns:
            List of metrics
        """
        return [m for m in self._metrics if m.name == name]

    def get_counter(self, name: str) -> float:
        """Get counter value.

        Args:
            name: Counter name

        Returns:
            Counter value
        """
        return self._counters.get(name, 0.0)

    def get_all_metrics(self) -> list[AgentMetric]:
        """Get all recorded metrics.

        Returns:
            List of all metrics
        """
        return self._metrics.copy()

    def clear_metrics(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()
        self._counters.clear()
        logger.info("metrics_cleared")


class ButlerAgentEvaluator:
    """Evaluator for agent performance.

    This evaluator:
    - Evaluates agent responses
    - Computes evaluation metrics
    - Supports custom evaluation criteria
    - Provides evaluation reports
    """

    def __init__(self):
        """Initialize the evaluator."""
        self._evaluations: list[dict[str, Any]] = []

    def evaluate_response(
        self,
        query: str,
        response: str,
        expected: str | None = None,
        criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate an agent response.

        Args:
            query: The query
            response: The response
            expected: Optional expected response
            criteria: Optional evaluation criteria

        Returns:
            Evaluation result
        """
        evaluation = {
            "query": query,
            "response": response,
            "expected": expected,
            "criteria": criteria or ["relevance", "coherence", "helpfulness"],
            "scores": {},
            "overall_score": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Compute scores for each criterion
        for criterion in evaluation["criteria"]:
            score = self._compute_score(criterion, query, response, expected)
            evaluation["scores"][criterion] = score

        # Compute overall score
        if evaluation["scores"]:
            evaluation["overall_score"] = sum(evaluation["scores"].values()) / len(evaluation["scores"])

        self._evaluations.append(evaluation)
        logger.info("agent_response_evaluated", overall_score=evaluation["overall_score"])
        return evaluation

    def _compute_score(
        self,
        criterion: str,
        query: str,
        response: str,
        expected: str | None,
    ) -> float:
        """Compute a score for a criterion.

        Args:
            criterion: The criterion
            query: The query
            response: The response
            expected: Expected response

        Returns:
            Score between 0 and 1
        """
        # Simple scoring logic
        # In production, this would use more sophisticated evaluation

        if criterion == "relevance":
            # Check if response relates to query
            return 0.8 if query.lower() in response.lower() else 0.5
        elif criterion == "coherence":
            # Check if response is coherent
            return 0.9 if len(response.split()) > 5 else 0.6
        elif criterion == "helpfulness":
            # Check if response is helpful
            return 0.85
        elif criterion == "accuracy" and expected:
            # Check if response matches expected
            return 1.0 if response.strip() == expected.strip() else 0.0
        else:
            return 0.7

    def evaluate_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        success: bool,
    ) -> dict[str, Any]:
        """Evaluate a tool call.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            result: Tool result
            success: Whether the call succeeded

        Returns:
            Evaluation result
        """
        evaluation = {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": str(result) if result is not None else None,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._evaluations.append(evaluation)
        logger.info("tool_call_evaluated", tool_name=tool_name, success=success)
        return evaluation

    def get_evaluations(self) -> list[dict[str, Any]]:
        """Get all evaluations.

        Returns:
            List of evaluations
        """
        return self._evaluations.copy()

    def get_average_score(self) -> float:
        """Get the average overall score.

        Returns:
            Average score
        """
        response_evals = [e for e in self._evaluations if "overall_score" in e]
        if not response_evals:
            return 0.0
        return sum(e["overall_score"] for e in response_evals) / len(response_evals)

    def get_success_rate(self) -> float:
        """Get the tool call success rate.

        Returns:
            Success rate between 0 and 1
        """
        tool_evals = [e for e in self._evaluations if "success" in e]
        if not tool_evals:
            return 0.0
        successful = sum(1 for e in tool_evals if e["success"])
        return successful / len(tool_evals)

    def generate_report(self) -> dict[str, Any]:
        """Generate an evaluation report.

        Returns:
            Evaluation report
        """
        return {
            "total_evaluations": len(self._evaluations),
            "average_score": self.get_average_score(),
            "success_rate": self.get_success_rate(),
            "response_evaluations": len([e for e in self._evaluations if "overall_score" in e]),
            "tool_evaluations": len([e for e in self._evaluations if "success" in e]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_evaluations(self) -> None:
        """Clear all evaluations."""
        self._evaluations.clear()
        logger.info("evaluations_cleared")


class ButlerObservability:
    """Combined observability suite.

    This suite:
    - Combines tracing, metrics, and evaluation
    - Provides unified observability interface
    - Supports export to external systems
    """

    def __init__(self, service_name: str = "butler-langchain"):
        """Initialize the observability suite.

        Args:
            service_name: Service name
        """
        self._tracer = ButlerAgentTracer(service_name)
        self._metrics = ButlerAgentMetrics()
        self._evaluator = ButlerAgentEvaluator()

    @property
    def tracer(self) -> ButlerAgentTracer:
        """Get the tracer."""
        return self._tracer

    @property
    def metrics(self) -> ButlerAgentMetrics:
        """Get the metrics collector."""
        return self._metrics

    @property
    def evaluator(self) -> ButlerAgentEvaluator:
        """Get the evaluator."""
        return self._evaluator

    def export_spans(self) -> list[dict[str, Any]]:
        """Export all spans.

        Returns:
            List of span dictionaries
        """
        all_spans = self._tracer.get_active_spans() + self._tracer.get_completed_spans()
        return [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "operation_name": s.operation_name,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "duration_ms": s.duration_ms,
                "status": s.status,
                "attributes": s.attributes,
                "events": s.events,
            }
            for s in all_spans
        ]

    def export_metrics(self) -> list[dict[str, Any]]:
        """Export all metrics.

        Returns:
            List of metric dictionaries
        """
        return [
            {
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "labels": m.labels,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in self._metrics.get_all_metrics()
        ]

    def export_evaluations(self) -> list[dict[str, Any]]:
        """Export all evaluations.

        Returns:
            List of evaluation dictionaries
        """
        return self._evaluator.get_evaluations()

    def export_all(self) -> dict[str, Any]:
        """Export all observability data.

        Returns:
            Dictionary with all data
        """
        return {
            "spans": self.export_spans(),
            "metrics": self.export_metrics(),
            "evaluations": self.export_evaluations(),
            "report": self._evaluator.generate_report(),
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_all(self) -> None:
        """Clear all observability data."""
        self._tracer.clear_completed_spans()
        self._metrics.clear_metrics()
        self._evaluator.clear_evaluations()
        logger.info("observability_cleared")
