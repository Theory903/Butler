"""Component Schemas.

Phase J: Component schemas for functional API using Pydantic.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MessageComponent(BaseModel):
    """Message component schema."""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ToolCallComponent(BaseModel):
    """Tool call component schema."""

    tool_name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(..., description="Tool arguments")
    result: Any | None = Field(None, description="Tool result")
    error: str | None = Field(None, description="Error message if tool failed")
    duration_ms: float | None = Field(None, description="Tool execution duration in milliseconds")


class AgentResponseComponent(BaseModel):
    """Agent response component schema."""

    content: str = Field(..., description="Response content")
    tool_calls: list[ToolCallComponent] = Field(default_factory=list, description="Tool calls made")
    reasoning: str | None = Field(None, description="Chain of thought reasoning")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Response confidence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class StreamingChunkComponent(BaseModel):
    """Streaming chunk component schema."""

    chunk: str = Field(..., description="Chunk content")
    index: int = Field(..., description="Chunk index")
    done: bool = Field(default=False, description="Whether this is the final chunk")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SessionComponent(BaseModel):
    """Session component schema."""

    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Session creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Session last update time"
    )
    messages: list[MessageComponent] = Field(default_factory=list, description="Session messages")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class AgentConfigComponent(BaseModel):
    """Agent configuration component schema."""

    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")
    role: str = Field(..., description="Agent role")
    model: str = Field(..., description="Model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=2048, gt=0, description="Maximum tokens")
    tools: list[str] = Field(default_factory=list, description="Available tools")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SkillComponent(BaseModel):
    """Skill component schema."""

    skill_id: str = Field(..., description="Skill identifier")
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    category: str = Field(..., description="Skill category")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Skill parameters")
    risk_level: str = Field(default="low", description="Risk level (low, medium, high)")
    is_installed: bool = Field(default=False, description="Whether skill is installed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class PluginComponent(BaseModel):
    """Plugin component schema."""

    plugin_id: str = Field(..., description="Plugin identifier")
    name: str = Field(..., description="Plugin name")
    version: str = Field(..., description="Plugin version")
    description: str = Field(..., description="Plugin description")
    author: str = Field(..., description="Plugin author")
    permissions: list[str] = Field(default_factory=list, description="Required permissions")
    is_active: bool = Field(default=False, description="Whether plugin is active")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
