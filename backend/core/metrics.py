from __future__ import annotations

import contextlib
from typing import Any

from opentelemetry import metrics

meter = metrics.get_meter("butler")

# Workflow
_workflow_started = meter.create_counter(
    "butler.workflow.started_total",
    description="Total workflows started",
)
_workflow_completed = meter.create_counter(
    "butler.workflow.completed_total",
    description="Total workflows completed successfully",
)
_workflow_failed = meter.create_counter(
    "butler.workflow.failed_total",
    description="Total workflows failed",
)
_workflow_duration = meter.create_histogram(
    "butler.workflow.duration_seconds",
    description="Workflow execution duration in seconds",
    unit="s",
)

# Tool
_tool_calls = meter.create_counter(
    "butler.tool.calls_total",
    description="Total tool invocations",
)
_tool_duration = meter.create_histogram(
    "butler.tool.duration_seconds",
    description="Tool execution duration in seconds",
    unit="s",
)

# Intent
_intent_classified = meter.create_counter(
    "butler.intent.classified_total",
    description="Total intents classified",
)
_intent_duration = meter.create_histogram(
    "butler.intent.classification_duration_seconds",
    description="Intent classification latency in seconds",
    unit="s",
)

# LLM
_llm_tokens = meter.create_counter(
    "butler.llm.tokens_total",
    description="Total LLM tokens consumed",
)

# Security
_injection_suspected = meter.create_counter(
    "butler.security.prompt_injection_suspected_total",
    description="Suspected prompt injection attempts",
)
_tool_blocked = meter.create_counter(
    "butler.security.tool_request_blocked_total",
    description="Tool requests blocked by policy",
)


class ButlerDomainMetrics:
    @staticmethod
    def workflow_started(workflow_name: str) -> None:
        _safe_add(_workflow_started, 1, {"workflow_name": workflow_name})

    @staticmethod
    def workflow_completed(workflow_name: str) -> None:
        _safe_add(_workflow_completed, 1, {"workflow_name": workflow_name})

    @staticmethod
    def workflow_failed(workflow_name: str, error_type: str) -> None:
        _safe_add(
            _workflow_failed,
            1,
            {"workflow_name": workflow_name, "error_type": error_type},
        )

    @staticmethod
    def workflow_duration(workflow_name: str, duration_seconds: float, status: str) -> None:
        _safe_record(
            _workflow_duration,
            duration_seconds,
            {"workflow_name": workflow_name, "status": status},
        )

    @staticmethod
    def tool_called(tool_name: str, risk_tier: str, success: bool) -> None:
        _safe_add(
            _tool_calls,
            1,
            {
                "tool_name": tool_name,
                "risk_tier": risk_tier,
                "success": str(success).lower(),
            },
        )

    @staticmethod
    def tool_duration(tool_name: str, duration_seconds: float) -> None:
        _safe_record(_tool_duration, duration_seconds, {"tool_name": tool_name})

    @staticmethod
    def intent_classified(intent_name: str, source: str = "unknown") -> None:
        _safe_add(
            _intent_classified,
            1,
            {"intent_name": intent_name, "source": source},
        )

    @staticmethod
    def intent_duration(intent_name: str, duration_seconds: float) -> None:
        _safe_record(
            _intent_duration,
            duration_seconds,
            {"intent_name": intent_name},
        )

    @staticmethod
    def llm_tokens(provider: str, model: str, token_type: str, count: int) -> None:
        _safe_add(
            _llm_tokens,
            count,
            {
                "provider": provider,
                "model": model,
                "token_type": token_type,
            },
        )

    @staticmethod
    def prompt_injection_suspected(source: str, route: str = "unknown") -> None:
        _safe_add(
            _injection_suspected,
            1,
            {"source": source, "route": route},
        )

    @staticmethod
    def tool_request_blocked(tool_name: str, policy: str) -> None:
        _safe_add(
            _tool_blocked,
            1,
            {"tool_name": tool_name, "policy": policy},
        )


def _safe_add(counter: Any, value: int, attributes: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        counter.add(value, attributes)


def _safe_record(histogram: Any, value: float, attributes: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        histogram.record(value, attributes)
