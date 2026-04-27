"""Canonical tool specifications for Butler runtime.

This is the single source of truth for all tool definitions.
Every tool must be registered here with full schema, risk tier, and policy metadata.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    """Risk classification for tools."""

    L0 = "L0"  # read-only local/deterministic
    L1 = "L1"  # low-risk external read/transform
    L2 = "L2"  # user-visible side effect
    L3 = "L3"  # high-risk irreversible/credential/system/browser action


class ApprovalMode(str, Enum):
    """Approval requirement mode for tools."""

    NONE = "none"  # no approval required
    OPTIONAL = "optional"  # approval optional based on policy
    REQUIRED = "required"  # approval always required
    HUMAN_IN_LOOP = "human_in_loop"  # requires human approval for each use


class ExecutableKind(str, Enum):
    """Kind of executable implementation."""

    DIRECT_FUNCTION = "direct_function"  # Python function call
    LANGCHAIN_TOOL = "langchain_tool"  # LangChain tool wrapper
    HTTP_ENDPOINT = "http_endpoint"  # External HTTP API
    WORKFLOW = "workflow"  # Durable workflow
    ASYNC_JOB = "async_job"  # Background job


class ButlerToolSpec(BaseModel):
    """Canonical specification for a Butler tool.

    This is the single source of truth for tool metadata.
    All tool registration, validation, and execution flows through this spec.
    """

    name: str
    version: str
    description: str
    owner: str
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    executable_kind: ExecutableKind
    binding_ref: str  # Reference to actual implementation
    timeout_ms: int
    idempotent: bool
    enabled: bool
    model_visible: bool  # Whether LLM can see this tool
    tags: list[str] = Field(default_factory=list)
    sandbox_required: bool = False
    max_retries: int = 3

    model_config = {"frozen": True}


# Initial tool specifications
GET_TIME_SPEC = ButlerToolSpec(
    name="get_time",
    version="1.0.0",
    description="Get the current date and time for a given timezone.",
    owner="tools",
    risk_tier=RiskTier.L0,
    approval_mode=ApprovalMode.NONE,
    input_schema={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name (e.g., 'UTC', 'America/New_York')",
                "default": "UTC",
            }
        },
        "required": [],
    },
    output_schema={
        "type": "object",
        "properties": {
            "timezone": {"type": "string"},
            "iso": {"type": "string"},
            "date": {"type": "string"},
            "time": {"type": "string"},
            "weekday": {"type": "string"},
            "unix_ms": {"type": "integer"},
        },
        "required": ["timezone", "iso", "date", "time", "weekday", "unix_ms"],
    },
    executable_kind=ExecutableKind.DIRECT_FUNCTION,
    binding_ref="butler_direct_tools:get_time_tool",
    timeout_ms=5000,
    idempotent=True,
    enabled=True,
    model_visible=True,
    tags=["time", "deterministic", "local"],
)

USER_CONTEXT_PROBE_SPEC = ButlerToolSpec(
    name="user_context_probe",
    version="1.0.0",
    description="Gather safe, normalized, privacy-aware context from request metadata, Client Hints, and optional client runtime context.",
    owner="context",
    risk_tier=RiskTier.L0,
    approval_mode=ApprovalMode.NONE,
    input_schema={
        "type": "object",
        "properties": {
            "request_id": {"type": "string"},
            "account_id": {"type": "string", "nullable": True},
            "session_id": {"type": "string", "nullable": True},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "remote_addr": {"type": "string", "nullable": True},
            "trusted_proxy_chain": {"type": "array", "items": {"type": "string"}, "default": []},
            "client_runtime_context": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "timezone": {"type": "string", "nullable": True},
                    "locale": {"type": "string", "nullable": True},
                    "screen": {
                        "type": "object",
                        "nullable": True,
                        "properties": {
                            "width": {"type": "integer", "nullable": True},
                            "height": {"type": "integer", "nullable": True},
                            "pixel_ratio": {"type": "number", "nullable": True},
                        },
                    },
                    "network": {
                        "type": "object",
                        "nullable": True,
                        "properties": {
                            "effective_type": {"type": "string", "nullable": True},
                            "downlink": {"type": "number", "nullable": True},
                            "rtt": {"type": "number", "nullable": True},
                            "save_data": {"type": "boolean", "nullable": True},
                        },
                    },
                    "geolocation": {
                        "type": "object",
                        "nullable": True,
                        "properties": {
                            "permission": {
                                "type": "string",
                                "enum": ["granted", "denied", "prompt", "unavailable"],
                            },
                            "coarse": {
                                "type": "object",
                                "nullable": True,
                                "properties": {
                                    "lat_rounded": {"type": "number", "nullable": True},
                                    "lon_rounded": {"type": "number", "nullable": True},
                                    "accuracy_m": {"type": "number", "nullable": True},
                                },
                            },
                        },
                    },
                },
            },
        },
        "required": ["request_id", "headers"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "request": {"type": "object"},
            "network": {"type": "object"},
            "device": {"type": "object"},
            "client_hints": {"type": "object"},
            "locale": {"type": "object"},
            "capabilities": {"type": "object"},
            "privacy": {"type": "object"},
            "trust": {"type": "object"},
        },
        "required": [
            "request",
            "network",
            "device",
            "client_hints",
            "locale",
            "capabilities",
            "privacy",
            "trust",
        ],
    },
    executable_kind=ExecutableKind.DIRECT_FUNCTION,
    binding_ref="context:user_context_probe",
    timeout_ms=3000,
    idempotent=True,
    enabled=True,
    model_visible=False,  # Not directly visible to LLM, used for context enrichment
    tags=["context", "privacy", "deterministic"],
)

# Placeholder for future tools
RAG_RETRIEVE_SPEC = ButlerToolSpec(
    name="rag_retrieve",
    version="1.0.0",
    description="Retrieve relevant documents, transcripts, or session history using RAG.",
    owner="retrieval",
    risk_tier=RiskTier.L1,
    approval_mode=ApprovalMode.NONE,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
            "source_types": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "required": ["query"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "results": {"type": "array"},
            "total": {"type": "integer"},
        },
        "required": ["results", "total"],
    },
    executable_kind=ExecutableKind.LANGCHAIN_TOOL,
    binding_ref="retrieval:rag_retrieve",
    timeout_ms=10000,
    idempotent=True,
    enabled=False,  # Disabled until implementation exists
    model_visible=True,
    tags=["retrieval", "rag"],
)

KAG_QUERY_SPEC = ButlerToolSpec(
    name="kag_query",
    version="1.0.0",
    description="Query knowledge graph for entities, relationships, and structured facts using KAG.",
    owner="retrieval",
    risk_tier=RiskTier.L1,
    approval_mode=ApprovalMode.NONE,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "entity_types": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "required": ["query"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "facts": {"type": "array"},
            "entities": {"type": "array"},
        },
        "required": ["facts", "entities"],
    },
    executable_kind=ExecutableKind.LANGCHAIN_TOOL,
    binding_ref="retrieval:kag_query",
    timeout_ms=10000,
    idempotent=True,
    enabled=False,  # Disabled until implementation exists
    model_visible=True,
    tags=["retrieval", "kag"],
)
