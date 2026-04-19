from abc import abstractmethod
from pydantic import BaseModel
from typing import Optional

from domain.base import DomainService
from domain.tools.models import ToolDefinition

class VerificationResult(BaseModel):
    passed: bool
    checks: list[tuple[str, bool]]
    reason: Optional[str] = None

class ToolResult(BaseModel):
    success: bool
    data: dict
    tool_name: str
    execution_id: str
    verification: VerificationResult
    compensation: Optional[dict] = None

class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str]

class ToolsServiceContract(DomainService):
    @abstractmethod
    async def execute(self, tool_name: str, params: dict, account_id: str, **kwargs) -> ToolResult:
        """Execute a tool with verification and audit."""
    
    @abstractmethod
    async def compensate(self, compensation_ref: dict) -> bool:
        """Run compensation handler to undo a tool's side-effects."""
    
    @abstractmethod
    async def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name."""
    
    @abstractmethod
    async def list_tools(self, category: Optional[str] = None) -> list[ToolDefinition]:
        """List available tools, optionally filtered by category."""
    
    @abstractmethod
    async def validate_params(self, tool_name: str, params: dict) -> ValidationResult:
        """Validate tool parameters against schema."""


class IToolVerifier(DomainService):
    """Abstraction over services.tools.verification.ToolVerifier.

    ToolExecutor depends on this contract so it can be tested with
    a no-op verifier without needing Redis/DB/approval infra.
    """

    @abstractmethod
    async def verify_preconditions(
        self,
        tool: "ToolDefinition",
        params: dict,
        account_id: str,
        account_tier: str = "free",
        approval_token: "Optional[str]" = None,
        session_scopes: "Optional[set[str]]" = None,
    ) -> "VerificationResult":
        """Check all preconditions before tool execution."""

    @abstractmethod
    async def verify_postconditions(
        self,
        tool: "ToolDefinition",
        params: dict,
        result: dict,
    ) -> "VerificationResult":
        """Check postconditions after tool execution."""
