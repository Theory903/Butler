from abc import abstractmethod

from pydantic import BaseModel

from domain.base import DomainService
from domain.tools.models import ToolDefinition


class VerificationResult(BaseModel):
    passed: bool
    checks: list[tuple[str, bool]]
    reason: str | None = None


class ToolResult(BaseModel):
    success: bool
    data: dict
    tool_name: str
    execution_id: str
    verification: VerificationResult
    compensation: dict | None = None


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
    async def get_tool(self, name: str) -> ToolDefinition | None:
        """Get tool definition by name."""

    @abstractmethod
    async def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
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
        approval_token: "str | None" = None,
        session_scopes: "set[str] | None" = None,
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
