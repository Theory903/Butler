"""Butler Workflow DAG — SOTA Durable Execution.

Defines the structure of Butler's Directed Acyclic Graph (DAG) for workflows.
Supports ASL-inspired semantics (BWL v1.0) with Butler-native logic.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
import uuid

class NodeKind(str, Enum):
    TASK = "task"                 # Execute a tool/function
    CHOICE = "choice"             # Branching logic (Switch)
    PARALLEL = "parallel"         # Concurrent execution branches
    MAP = "map"                   # Iteration over a list
    WAIT = "wait"                 # Suspend for duration or timestamp
    SIGNAL_WAIT = "signal_wait"   # Suspend for external async signal
    PASS = "pass"                 # No-op / state transformation
    FAIL = "fail"                 # Terminal failure state
    SUCCESS = "success"           # Terminal success state
    APPROVAL = "approval"         # Suspend for human decision (ACP)
    COMPENSATION = "compensation" # Rollback logic for a specific node
    POLICY_GATE = "policy_gate"   # Enforce governance/safety

class ChoiceRule(BaseModel):
    variable: str
    operator: str  # StringEquals, NumericLessThan, etc.
    value: Any
    next: str

class DAGNode(BaseModel):
    id: str = Field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    kind: NodeKind
    
    # Task / Tool props
    tool_name: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    
    # Branching (Choice)
    choices: Optional[List[ChoiceRule]] = None
    default_next: Optional[str] = None
    
    # Parallelism
    branches: Optional[List[WorkflowDAG]] = None
    
    # Iteration (Map)
    items_path: Optional[str] = None
    item_processor: Optional[WorkflowDAG] = None
    
    # Connectivity
    next: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    
    # Resilience
    timeout_s: int = 3600
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {"max_retries": 3, "backoff": "exponential"})
    compensation_node_id: Optional[str] = None
    
    # Context
    metadata: Dict[str, Any] = Field(default_factory=dict)

class WorkflowDAG(BaseModel):
    nodes: List[DAGNode]
    start_at: str
    version: str = "2.0"

    @field_validator("nodes")
    @classmethod
    def validate_dag(cls, v: List[DAGNode]) -> List[DAGNode]:
        node_ids = {n.id for n in v}
        for node in v:
            # Check direct next
            if node.next and node.next not in node_ids:
                raise ValueError(f"Destination {node.next} not found for node {node.id}")
            
            # Check choices
            if node.choices:
                for choice in node.choices:
                    if choice.next not in node_ids:
                        raise ValueError(f"Choice destination {choice.next} not found for node {node.id}")
            
            # Check default choice
            if node.default_next and node.default_next not in node_ids:
                raise ValueError(f"Default destination {node.default_next} not found for node {node.id}")
                
        return v

class PlanLowerer:
    """Auto-lowers linear Plan objects into sequential DAGs for backward compatibility."""

    @staticmethod
    def lower(plan: Any) -> WorkflowDAG:
        """Lower a legacy Plan into a Butler Workflow DAG.
        
        A linear plan becomes a chain of nodes where each node points to the next.
        """
        nodes = []
        steps = getattr(plan, "steps", [])
        
        if not steps:
            # Return empty but valid DAG
            success_node = DAGNode(id="terminal_success", kind=NodeKind.SUCCESS)
            return WorkflowDAG(nodes=[success_node], start_at="terminal_success")

        for i, step in enumerate(steps):
            node_id = f"step_{i}_{step.action}"
            next_id = None
            if i < len(steps) - 1:
                next_step = steps[i+1]
                next_id = f"step_{i+1}_{next_step.action}"
            else:
                next_id = "terminal_success"
            
            # Map legacy action to NodeKind
            kind = NodeKind.TASK
            if step.action == "approval":
                kind = NodeKind.APPROVAL
            
            node = DAGNode(
                id=node_id,
                kind=kind,
                tool_name=step.action,
                inputs=step.params,
                next=next_id,
            )
            nodes.append(node)
        
        # Add terminal success
        nodes.append(DAGNode(id="terminal_success", kind=NodeKind.SUCCESS))

        return WorkflowDAG(nodes=nodes, start_at=nodes[0].id)
