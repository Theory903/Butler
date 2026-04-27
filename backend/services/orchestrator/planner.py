from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from domain.orchestration.router import OperationRequest, OperationRouter, OperationType
from domain.orchestrator.contracts import (
    ExecutionMode,
    ExecutionPlan,
    PlannerSource,
    PlanStepContract,
    RiskLevel,
)

logger = structlog.get_logger(__name__)


class Step(BaseModel):
    """Backward-compatible linear plan step."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Step action must not be empty")
        return normalized


class Plan(BaseModel):
    """Backward-compatible linear plan representation.

    This remains for compatibility with the current executor/lowerer path while
    the richer ExecutionPlan contract becomes the canonical planning shape.
    """

    model_config = ConfigDict(extra="forbid")

    steps: list[Step] = Field(default_factory=list)
    intent: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.WORKFLOW
    planner_source: PlannerSource = PlannerSource.DETERMINISTIC
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("intent must not be empty")
        return normalized

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_execution_plan(cls, execution_plan: ExecutionPlan) -> Plan:
        """Convert canonical execution plan into the current linear plan shape."""
        return cls(
            steps=[
                Step(
                    action=step.action,
                    params=step.params,
                )
                for step in execution_plan.steps
            ],
            intent=execution_plan.intent,
            context=execution_plan.context,
            execution_mode=execution_plan.execution_mode,
            planner_source=execution_plan.planner_source,
            risk_level=execution_plan.risk_level,
            requires_approval=execution_plan.requires_approval,
            metadata=execution_plan.planner_metadata,
        )


class PlannerModelOutput(BaseModel):
    """Structured model output for planning."""

    model_config = ConfigDict(extra="forbid")

    goal: str = ""
    intent: str = Field(min_length=1)
    execution_mode: ExecutionMode = ExecutionMode.WORKFLOW
    planner_source: PlannerSource = PlannerSource.LLM
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    steps: list[PlanStepContract] = Field(default_factory=list)
    planner_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("intent must not be empty")
        return normalized


class PlannerBackend(Protocol):
    """Contract for planner-generation backends."""

    async def generate_plan(
        self,
        *,
        intent: str,
        context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        system_prompt: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Return a structured planning payload."""


class LLMPlannerBackend(PlannerBackend):
    """LLM-driven implementation of the planner backend."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def generate_plan(
        self,
        *,
        intent: str,
        context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        system_prompt: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        from domain.ml.contracts import ReasoningRequest, ReasoningTier

        request = ReasoningRequest(
            prompt=f"Goal: {intent}\nContext: {context}",
            system_prompt=system_prompt,
            preferred_tier=ReasoningTier.T2,
            response_format="json",
        )

        response = await self._runtime.generate(request, tenant_id=tenant_id)
        import json

        try:
            return json.loads(response.content)
        except (json.JSONDecodeError, TypeError):
            # Fallback to empty steps if LLM fails to return JSON
            return {
                "goal": intent,
                "intent": intent,
                "steps": [],
                "execution_mode": "agentic",
            }


@dataclass(frozen=True)
class PlannerPolicy:
    """Planning policy knobs."""

    max_steps: int = 12
    allow_llm_planning: bool = True
    fallback_execution_mode: ExecutionMode = ExecutionMode.AGENTIC


class PlanEngine:
    """Create executable plans for Butler.

    Design:
    - LLM/hybrid planning is the default when a planner backend is available
    - deterministic fallback remains as a safety rail
    - all outputs are normalized through a strict schema
    - router checks admission for tool operations before planning
    """

    def __init__(
        self,
        planner_backend: PlannerBackend | None = None,
        *,
        policy: PlannerPolicy | None = None,
        available_tools_provider: callable | None = None,
        router: OperationRouter | None = None,
    ) -> None:
        self._planner_backend = planner_backend
        self._policy = policy or PlannerPolicy()
        self._available_tools_provider = available_tools_provider
        self._router = router

    async def create_plan(
        self, intent: str, context: dict[str, Any] | None, tenant_id: str = "default"
    ) -> Plan:
        """Create an execution plan.

        Uses model-based planning when available. Falls back to deterministic
        planning when the planner backend is absent or returns invalid output.
        """
        normalized_intent = self._normalize_intent(intent)
        normalized_context = self._normalize_context(context)
        account_id = context.get("account_id", tenant_id) if context else tenant_id
        available_tools = self._get_available_tools(tenant_id, account_id)

        logger.info(
            "planner_create_plan_started",
            intent=normalized_intent,
            tool_count=len(available_tools),
            llm_enabled=self._planner_backend is not None and self._policy.allow_llm_planning,
        )

        if self._planner_backend is not None and self._policy.allow_llm_planning:
            try:
                execution_plan = await self._generate_model_plan(
                    intent=normalized_intent,
                    context=normalized_context,
                    available_tools=available_tools,
                    tenant_id=tenant_id,
                )
                linear_plan = Plan.from_execution_plan(execution_plan)
                logger.info(
                    "planner_create_plan_succeeded",
                    source="llm",
                    intent=linear_plan.intent,
                    step_count=len(linear_plan.steps),
                    execution_mode=linear_plan.execution_mode.value,
                )
                return linear_plan
            except Exception:
                logger.exception(
                    "planner_model_plan_failed",
                    intent=normalized_intent,
                )

        fallback_plan = self._build_fallback_plan(
            intent=normalized_intent,
            context=normalized_context,
        )
        logger.info(
            "planner_create_plan_succeeded",
            source="fallback",
            intent=fallback_plan.intent,
            step_count=len(fallback_plan.steps),
            execution_mode=fallback_plan.execution_mode.value,
        )
        return fallback_plan

    def _check_tool_admission(
        self,
        tool_name: str,
        tenant_id: str,
        account_id: str,
    ) -> bool:
        """Check if tool operation is allowed through router admission."""
        if self._router is None:
            return True

        from domain.orchestration.router import AdmissionDecision

        operation_request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=None,
            tool_name=tool_name,
            risk_tier=None,
            estimated_cost=None,
        )

        _, admission = self._router.route(operation_request)
        return admission.decision == AdmissionDecision.ALLOW

    async def _generate_model_plan(
        self,
        *,
        intent: str,
        context: dict[str, Any],
        available_tools: list[dict[str, Any]],
        tenant_id: str = "default",
    ) -> ExecutionPlan:
        """Generate and validate an LLM/hybrid plan."""
        if self._planner_backend is None:
            raise RuntimeError("Planner backend is not configured")

        system_prompt = self._build_planner_system_prompt(
            intent=intent,
            context=context,
            available_tools=available_tools,
        )

        raw_payload = await self._planner_backend.generate_plan(
            intent=intent,
            context=context,
            available_tools=available_tools,
            system_prompt=system_prompt,
            tenant_id=tenant_id,
        )

        try:
            structured = PlannerModelOutput.model_validate(raw_payload)
        except ValidationError as exc:
            raise ValueError(f"Planner model output failed validation: {exc}") from exc

        if not structured.steps:
            raise ValueError("Planner model returned no steps")

        if len(structured.steps) > self._policy.max_steps:
            raise ValueError(
                f"Planner model exceeded max steps: {len(structured.steps)} > {self._policy.max_steps}"
            )

        normalized_steps = self._normalize_model_steps(
            structured.steps,
            available_tools=available_tools,
        )

        return ExecutionPlan(
            goal=structured.goal,
            intent=structured.intent,
            execution_mode=structured.execution_mode,
            planner_source=structured.planner_source,
            risk_level=structured.risk_level,
            requires_approval=structured.requires_approval,
            steps=normalized_steps,
            context=context,
            planner_metadata=structured.planner_metadata,
        )

    def _normalize_model_steps(
        self,
        steps: list[PlanStepContract],
        *,
        available_tools: list[dict[str, Any]],
    ) -> list[PlanStepContract]:
        """Normalize and validate generated steps."""
        tool_names = {str(tool.get("name")) for tool in available_tools if tool.get("name")}

        normalized_steps: list[PlanStepContract] = []
        seen_ids: set[str] = set()

        for index, step in enumerate(steps):
            step_id = step.id.strip() or self._build_step_id(index, step.action)
            if step_id in seen_ids:
                step_id = self._build_step_id(index, step.action)
            seen_ids.add(step_id)

            depends_on = [dependency for dependency in step.depends_on if dependency in seen_ids]

            tool_name = step.tool_name
            if tool_name is not None and tool_names and tool_name not in tool_names:
                logger.warning(
                    "planner_unknown_tool_generated",
                    tool_name=tool_name,
                    action=step.action,
                    step_id=step_id,
                )
                tool_name = None

            normalized_steps.append(
                PlanStepContract(
                    id=step_id,
                    action=step.action.strip(),
                    kind=step.kind.strip(),
                    params=dict(step.params),
                    depends_on=depends_on,
                    tool_name=tool_name,
                    requires_approval=step.requires_approval,
                    timeout_s=step.timeout_s,
                    retry_policy=dict(step.retry_policy),
                    metadata=dict(step.metadata),
                )
            )

        return normalized_steps

    def _build_fallback_plan(
        self,
        *,
        intent: str,
        context: dict[str, Any],
    ) -> Plan:
        user_prompt = self._extract_user_prompt(context)

        if self._is_time_query(user_prompt):
            return Plan(
                steps=[Step(action="get_time", params={})],
                intent=intent,
                context=context,
                execution_mode=ExecutionMode.DETERMINISTIC,
                planner_source=PlannerSource.DETERMINISTIC,
                risk_level=RiskLevel.LOW,
            )

        if self._is_news_query(user_prompt):
            return Plan(
                steps=[
                    Step(
                        action="web_search",
                        params={
                            "query": user_prompt,
                            "mode": "current_events",
                            "max_results": 5,
                        },
                    )
                ],
                intent=intent,
                context=context,
                execution_mode=ExecutionMode.DETERMINISTIC,
                planner_source=PlannerSource.DETERMINISTIC,
                risk_level=RiskLevel.LOW,
            )

        steps = [
            Step(
                action="respond",
                params={
                    "response_type": "general",
                    "message": user_prompt,
                },
            ),
        ]
        return Plan(
            steps=steps,
            intent=intent,
            context=context,
            execution_mode=self._policy.fallback_execution_mode,
            planner_source=PlannerSource.DETERMINISTIC,
            risk_level=RiskLevel.LOW,
        )

    def _build_planner_system_prompt(
        self,
        *,
        intent: str,
        context: dict[str, Any],
        available_tools: list[dict[str, Any]],
    ) -> str:
        """Build the planner prompt for structured plan generation."""
        tool_lines = []
        for tool in available_tools[:100]:
            name = str(tool.get("name", "")).strip()
            description = str(tool.get("description", "")).strip()
            if name:
                tool_lines.append(f"- {name}: {description}")

        context_summary = self._summarize_context(context)

        return (
            "You are Butler's planning engine.\n"
            "Produce a structured execution plan for the user's goal.\n"
            "Prefer the simplest valid plan.\n"
            "Use available tools only when necessary.\n"
            "Mark steps that likely require approval.\n"
            "Avoid unnecessary steps.\n"
            "Do not invent tools that are not listed.\n"
            "Return a structured plan only.\n\n"
            f"Resolved intent: {intent}\n"
            f"Context summary: {context_summary}\n"
            "Available tools:\n"
            + ("\n".join(tool_lines) if tool_lines else "- none explicitly provided")
        )

    def _get_available_tools(
        self, tenant_id: str = "default", account_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return normalized planner-visible tool metadata filtered by router admission."""
        if self._available_tools_provider is None:
            return []

        try:
            raw_tools = self._available_tools_provider() or []
        except Exception:
            logger.exception("planner_available_tools_provider_failed")
            return []

        normalized: list[dict[str, Any]] = []
        for tool in raw_tools:
            if isinstance(tool, dict):
                name = tool.get("name")
                if name:
                    # Check tool admission through router
                    if self._check_tool_admission(str(name), tenant_id, account_id or tenant_id):
                        normalized.append(
                            {
                                "name": str(name),
                                "description": str(tool.get("description", "")),
                                "metadata": dict(tool.get("metadata", {}) or {}),
                            }
                        )
                continue

            name = getattr(tool, "name", None)
            if name:
                # Check tool admission through router
                if self._check_tool_admission(str(name), tenant_id, account_id or tenant_id):
                    normalized.append(
                        {
                            "name": str(name),
                            "description": str(getattr(tool, "description", "")),
                            "metadata": dict(getattr(tool, "metadata", {}) or {}),
                        }
                    )

        return normalized

    def _normalize_intent(self, intent: str | None) -> str:
        normalized = (intent or "").strip().lower()
        return normalized or "unknown"

    def _normalize_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if context is None:
            return {}
        return dict(context)

    def _extract_user_prompt(self, context: dict[str, Any]) -> str:
        for key in ("prompt", "message", "query"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _summarize_context(self, context: dict[str, Any]) -> str:
        if not context:
            return "no additional context"

        parts: list[str] = []
        for key in ("prompt", "message", "query", "channel", "mode"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                collapsed = re.sub(r"\s+", " ", value.strip())
                parts.append(f"{key}={collapsed[:240]}")

        return "; ".join(parts) if parts else "structured context provided"

    def _build_step_id(self, index: int, action: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", action.strip().lower()).strip("_")
        slug = slug or "step"
        return f"step_{index}_{slug}"

    def _is_time_query(self, prompt: str) -> bool:
        normalized = (prompt or "").strip().lower()
        if not normalized:
            return False

        time_markers = (
            "current time",
            "what time is it",
            "time now",
            "time is it",
            "local time",
        )
        return any(marker in normalized for marker in time_markers)

    def _is_news_query(self, prompt: str) -> bool:
        normalized = (prompt or "").strip().lower()
        if not normalized:
            return False

        news_markers = (
            "news",
            "latest",
            "current events",
            "what's happening",
            "what is happening",
            "headlines",
            "update on",
        )
        geography_markers = (
            "iran",
            "usa",
            "u.s.",
            "united states",
        )
        return any(marker in normalized for marker in news_markers) and any(
            marker in normalized for marker in geography_markers
        )
