"""CrewAI configuration for Butler integration.

This module provides configuration classes for CrewAI integration
within Butler, maintaining Butler's security and governance boundaries.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CrewAIConfig(BaseModel):
    """Configuration for CrewAI integration.

    This configuration controls how CrewAI agents and crews are
    instantiated and configured within Butler's execution framework.
    """

    # LLM configuration
    model: str = Field(default="openai/gpt-4o", description="Model to use for CrewAI agents")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Temperature for LLM responses")
    max_tokens: int = Field(default=4000, ge=1, description="Maximum tokens for LLM responses")

    # Crew configuration
    process: str = Field(default="sequential", description="Process type: sequential or hierarchical")
    memory: bool = Field(default=True, description="Enable CrewAI memory")
    verbose: bool = Field(default=False, description="Enable verbose logging")

    # Butler integration
    enable_security_guardrails: bool = Field(
        default=True, description="Pass through Butler ContentGuard and RedactionService"
    )
    enable_memory_integration: bool = Field(
        default=True, description="Integrate with Butler MemoryService"
    )
    max_execution_time_seconds: int = Field(
        default=300, ge=1, description="Maximum execution time for CrewAI operations"
    )

    # Checkpointing
    enable_checkpointing: bool = Field(
        default=False, description="Enable CrewAI checkpointing (uses Butler durability by default)"
    )

    class Config:
        """Pydantic config."""

        extra = "forbid"


class CrewAgentConfig(BaseModel):
    """Configuration for a single CrewAI agent.

    Defines the role, goal, backstory, and other attributes
    for a CrewAI agent within Butler's framework.
    """

    role: str = Field(..., description="Agent role (e.g., 'Research Specialist')")
    goal: str = Field(..., description="Agent goal (e.g., 'Conduct comprehensive research')")
    backstory: str = Field(..., description="Agent backstory and context")
    verbose: bool = Field(default=False, description="Enable verbose logging for this agent")
    allow_delegation: bool = Field(default=True, description="Allow task delegation to other agents")
    llm: str | None = Field(default=None, description="Override default LLM for this agent")

    # Butler-specific attributes
    safety_class: str = Field(
        default="safe_auto", description="Safety class: safe_auto, confirm, restricted"
    )
    requires_approval: bool = Field(default=False, description="Whether this agent requires approval")

    class Config:
        """Pydantic config."""

        extra = "forbid"


class CrewTaskConfig(BaseModel):
    """Configuration for a CrewAI task.

    Defines the description, expected output, and other attributes
    for a CrewAI task within Butler's framework.
    """

    description: str = Field(..., description="Task description")
    expected_output: str = Field(..., description="Expected output format")
    agent: str = Field(..., description="Agent role to assign this task to")
    async_execution: bool = Field(default=False, description="Execute task asynchronously")

    class Config:
        """Pydantic config."""

        extra = "forbid"


class DomainRequirement(BaseModel):
    """Domain requirements for CrewAI crew building.

    Used by the intent router to specify domain-specific
    requirements for CrewAI execution.
    """

    domain: str = Field(..., description="Domain name (e.g., 'research', 'financial_analysis')")
    complexity: str = Field(default="medium", description="Complexity: low, medium, high")
    requires_multi_agent: bool = Field(default=True, description="Whether multi-agent collaboration is needed")
    agent_roles: list[str] = Field(default_factory=list, description="Required agent roles")
    tools: list[str] = Field(default_factory=list, description="Required tools")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional domain metadata")

    class Config:
        """Pydantic config."""

        extra = "forbid"
