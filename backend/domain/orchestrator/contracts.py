from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.envelope import ButlerEnvelope
from domain.base import DomainService
from domain.orchestrator.models import ApprovalRequest, Task, Workflow


class ExecutionMode(StrEnum):
    """How Butler intends to execute a request."""

    DETERMINISTIC = "deterministic"
    AGENTIC = "agentic"
    WORKFLOW = "workflow"
    SUBAGENT = "subagent"


class PlannerSource(StrEnum):
    """Where a plan originated."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HYBRID = "hybrid"


class RiskLevel(StrEnum):
    """Planner or execution risk tier."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionRecord(BaseModel):
    """Canonical record of an executed or proposed action."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    status: str = Field(min_length=1)
    tool_name: str | None = None
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action", "status")
    @classmethod
    def validate_non_empty_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized


class PlanStepContract(BaseModel):
    """Stable planning-step contract for planner and orchestrator integration."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    kind: str = Field(default="task", min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    requires_approval: bool = False
    timeout_s: int = Field(default=3600, ge=1, le=86_400)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "action", "kind")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Field must not be empty")
        return normalized


class ExecutionPlan(BaseModel):
    """Canonical execution plan contract.

    This is intentionally richer than the current planner implementation so the
    planner can evolve toward LLM/hybrid generation without changing the
    orchestration boundary every week.
    """

    model_config = ConfigDict(extra="forbid")

    goal: str = ""
    intent: str = Field(min_length=1)
    execution_mode: ExecutionMode = ExecutionMode.WORKFLOW
    planner_source: PlannerSource = PlannerSource.DETERMINISTIC
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    steps: list[PlanStepContract] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    planner_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("intent must not be empty")
        return normalized


class OrchestratorResult(BaseModel):
    """Canonical response format for orchestrator ingestion and completion."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    content: str
    actions: list[ActionRecord] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    requires_approval: bool = False
    approval_id: str | None = None
    execution_mode: ExecutionMode | None = None
    planner_source: PlannerSource | None = None
    risk_level: RiskLevel | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


ApprovalDecision = Literal["approved", "denied"]


class OrchestratorServiceContract(DomainService):
    """Primary orchestrator service boundary."""

    @abstractmethod
    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        """Receive an envelope, orchestrate execution, and return the result."""
        raise NotImplementedError

    @abstractmethod
    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Return a workflow by id."""
        raise NotImplementedError

    @abstractmethod
    async def approve_request(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        account_id: str | None = None,
    ) -> Task:
        """Apply a human approval decision to a pending approval request."""
        raise NotImplementedError

    @abstractmethod
    async def get_pending_approvals(self, account_id: str) -> list[ApprovalRequest]:
        """List pending approval requests for an account."""
        raise NotImplementedError

    @abstractmethod
    async def retry_task(self, task_id: str) -> Task:
        """Retry a failed task."""
        raise NotImplementedError

    @abstractmethod
    async def record_interaction_outcome(
        self,
        user_id: str,
        tool_id: str,
        success: bool,
    ) -> None:
        """Record the success or failure of an interaction for personalization."""
        raise NotImplementedError
