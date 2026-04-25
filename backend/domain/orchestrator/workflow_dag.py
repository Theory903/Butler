"""Butler Workflow DAG — durable workflow graph model.

Defines the canonical structure of Butler's directed acyclic workflow graph.

Design goals:
- explicit node semantics
- durable validation before runtime execution
- compatibility with legacy linear plans via lowering
- safe recursive structure for PARALLEL and MAP nodes
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NodeKind(StrEnum):
    """Supported workflow node kinds."""

    TASK = "task"
    CHOICE = "choice"
    PARALLEL = "parallel"
    MAP = "map"
    WAIT = "wait"
    SIGNAL_WAIT = "signal_wait"
    PASS = "pass"
    FAIL = "fail"
    SUCCESS = "success"
    APPROVAL = "approval"
    COMPENSATION = "compensation"
    POLICY_GATE = "policy_gate"


class RetryPolicy(BaseModel):
    """Retry policy for a node."""

    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=3, ge=0, le=20)
    backoff: str = Field(default="exponential")
    base_delay_ms: int = Field(default=500, ge=0)
    max_delay_ms: int = Field(default=30_000, ge=0)

    @field_validator("backoff")
    @classmethod
    def validate_backoff(cls, value: str) -> str:
        allowed = {"none", "fixed", "linear", "exponential"}
        if value not in allowed:
            raise ValueError(f"Unsupported backoff strategy: {value!r}")
        return value

    @model_validator(mode="after")
    def validate_delay_order(self) -> RetryPolicy:
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max_delay_ms must be greater than or equal to base_delay_ms")
        return self


class ChoiceRule(BaseModel):
    """Branch rule for a CHOICE node."""

    model_config = ConfigDict(extra="forbid")

    variable: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: Any
    next: str = Field(min_length=1)


class DAGNode(BaseModel):
    """One node in a Butler workflow DAG."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    kind: NodeKind

    # Task / Tool props
    tool_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)

    # Branching
    choices: list[ChoiceRule] | None = None
    default_next: str | None = None

    # Parallelism
    branches: list[WorkflowDAG] | None = None

    # Iteration
    items_path: str | None = None
    item_processor: WorkflowDAG | None = None

    # Wait / signal / approval
    wait_for_s: int | None = Field(default=None, ge=0)
    wait_until: str | None = None
    signal_name: str | None = None
    approval_kind: str | None = None

    # Connectivity
    next: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    # Resilience / recovery
    timeout_s: int = Field(default=3600, ge=1, le=86_400)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    compensation_node_id: str | None = None

    # Context / metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Node id must not be empty")
        return value

    @model_validator(mode="after")
    def validate_node_shape(self) -> DAGNode:
        """Validate fields required and forbidden per node kind."""
        kind = self.kind

        if kind == NodeKind.TASK and not self.tool_name:
            raise ValueError("TASK node requires tool_name")

        if kind == NodeKind.CHOICE and not self.choices:
            raise ValueError("CHOICE node requires at least one choice rule")

        if kind == NodeKind.PARALLEL:
            if not self.branches:
                raise ValueError("PARALLEL node requires branches")
            if self.next is None:
                raise ValueError("PARALLEL node requires next")

        if kind == NodeKind.MAP:
            if not self.items_path:
                raise ValueError("MAP node requires items_path")
            if self.item_processor is None:
                raise ValueError("MAP node requires item_processor")
            if self.next is None:
                raise ValueError("MAP node requires next")

        if kind == NodeKind.WAIT:
            if self.wait_for_s is None and self.wait_until is None:
                raise ValueError("WAIT node requires wait_for_s or wait_until")
            if self.wait_for_s is not None and self.wait_until is not None:
                raise ValueError("WAIT node must not define both wait_for_s and wait_until")

        if kind == NodeKind.SIGNAL_WAIT and not self.signal_name:
            raise ValueError("SIGNAL_WAIT node requires signal_name")

        if kind == NodeKind.APPROVAL and not self.approval_kind:
            self.approval_kind = "tool_execution"

        if kind in {NodeKind.SUCCESS, NodeKind.FAIL} and self.next is not None:
            raise ValueError(f"{kind.value.upper()} node must not define next")

        return self


class WorkflowDAG(BaseModel):
    """Durable workflow graph."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[DAGNode]
    start_at: str = Field(min_length=1)
    version: str = "2.0"

    @model_validator(mode="after")
    def validate_dag(self) -> WorkflowDAG:
        """Validate internal graph consistency."""
        if not self.nodes:
            raise ValueError("WorkflowDAG must contain at least one node")

        node_ids = [node.id for node in self.nodes]
        node_id_set = set(node_ids)

        if len(node_ids) != len(node_id_set):
            duplicates = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
            raise ValueError(f"Duplicate node ids are not allowed: {duplicates}")

        if self.start_at not in node_id_set:
            raise ValueError(f"start_at references unknown node: {self.start_at!r}")

        for node in self.nodes:
            self._validate_node_references(node, node_id_set)

        if not self._has_terminal_node():
            raise ValueError("WorkflowDAG must contain at least one terminal SUCCESS or FAIL node")

        return self

    def get_node(self, node_id: str) -> DAGNode | None:
        """Return a node by id."""
        return next((node for node in self.nodes if node.id == node_id), None)

    def _validate_node_references(self, node: DAGNode, node_ids: set[str]) -> None:
        if node.next and node.next not in node_ids:
            raise ValueError(f"Destination {node.next!r} not found for node {node.id!r}")

        if node.default_next and node.default_next not in node_ids:
            raise ValueError(f"default_next {node.default_next!r} not found for node {node.id!r}")

        for dependency in node.depends_on:
            if dependency not in node_ids:
                raise ValueError(f"depends_on target {dependency!r} not found for node {node.id!r}")
            if dependency == node.id:
                raise ValueError(f"Node {node.id!r} cannot depend on itself")

        if node.compensation_node_id:
            if node.compensation_node_id not in node_ids:
                raise ValueError(
                    f"compensation_node_id {node.compensation_node_id!r} not found for node {node.id!r}"
                )
            if node.compensation_node_id == node.id:
                raise ValueError(f"Node {node.id!r} cannot compensate itself")

        if node.choices:
            for choice in node.choices:
                if choice.next not in node_ids:
                    raise ValueError(
                        f"Choice destination {choice.next!r} not found for node {node.id!r}"
                    )

    def _has_terminal_node(self) -> bool:
        return any(node.kind in {NodeKind.SUCCESS, NodeKind.FAIL} for node in self.nodes)


class PlanLowerer:
    """Lower legacy linear plans into Butler Workflow DAGs."""

    @staticmethod
    def lower(plan: Any) -> WorkflowDAG:
        """Lower a legacy plan into a sequential Butler DAG."""
        steps = list(getattr(plan, "steps", []) or [])

        if not steps:
            success_node = DAGNode(id="terminal_success", kind=NodeKind.SUCCESS)
            return WorkflowDAG(nodes=[success_node], start_at=success_node.id)

        nodes: list[DAGNode] = []

        for index, step in enumerate(steps):
            action = str(getattr(step, "action", "task") or "task")
            params = getattr(step, "params", {}) or {}
            node_id = PlanLowerer._build_step_id(index, action)

            if index < len(steps) - 1:
                next_action = str(getattr(steps[index + 1], "action", "task") or "task")
                next_id = PlanLowerer._build_step_id(index + 1, next_action)
            else:
                next_id = "terminal_success"

            kind = PlanLowerer._infer_kind(action)

            node_kwargs: dict[str, Any] = {
                "id": node_id,
                "kind": kind,
                "inputs": params if isinstance(params, dict) else {"value": params},
                "next": next_id,
            }

            if kind == NodeKind.TASK:
                node_kwargs["tool_name"] = action
            elif kind == NodeKind.APPROVAL:
                node_kwargs["approval_kind"] = "tool_execution"
                node_kwargs["tool_name"] = action
            elif kind == NodeKind.SIGNAL_WAIT:
                signal_name = params.get("signal_name") if isinstance(params, dict) else None
                node_kwargs["signal_name"] = signal_name or "external_signal"
            elif kind == NodeKind.WAIT:
                if isinstance(params, dict):
                    if "wait_for_s" in params:
                        node_kwargs["wait_for_s"] = params["wait_for_s"]
                    elif "wait_until" in params:
                        node_kwargs["wait_until"] = params["wait_until"]
                    else:
                        node_kwargs["wait_for_s"] = 0
                else:
                    node_kwargs["wait_for_s"] = 0

            nodes.append(DAGNode(**node_kwargs))

        nodes.append(DAGNode(id="terminal_success", kind=NodeKind.SUCCESS))
        return WorkflowDAG(nodes=nodes, start_at=nodes[0].id)

    @staticmethod
    def _infer_kind(action: str) -> NodeKind:
        normalized = action.strip().lower()

        if normalized == "approval":
            return NodeKind.APPROVAL
        if normalized in {"wait", "sleep", "delay"}:
            return NodeKind.WAIT
        if normalized in {"signal_wait", "await_signal"}:
            return NodeKind.SIGNAL_WAIT
        if normalized == "pass":
            return NodeKind.PASS
        if normalized == "fail":
            return NodeKind.FAIL
        if normalized == "success":
            return NodeKind.SUCCESS
        return NodeKind.TASK

    @staticmethod
    def _build_step_id(index: int, action: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", action.strip().lower()).strip("_")
        slug = slug or "step"
        return f"step_{index}_{slug}"


WorkflowDAG.model_rebuild()
DAGNode.model_rebuild()
