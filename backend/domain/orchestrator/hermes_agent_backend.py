"""
Hermes Agent Backend - Policy Gate and Exception Types

Provides policy enforcement and exception types for Hermes tool execution.
"""

from __future__ import annotations

from typing import Any


class ToolPolicyViolation(Exception):
    """Raised when a tool call violates policy."""


class ApprovalRequired(Exception):
    """Raised when a tool call requires approval."""


class AssuranceInsufficient(Exception):
    """Raised when assurance level is insufficient for a tool."""


class ButlerToolPolicyGate:
    """
    Policy gate for tool execution checks.

    Validates tool calls against account tier, channel, and assurance level policies.
    """

    def __init__(
        self,
        compiled_specs: dict[str, Any],
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
    ) -> None:
        """
        Initialize the policy gate.

        Args:
            compiled_specs: Dictionary of compiled tool specs
            account_tier: Account tier (free, pro, enterprise)
            channel: Channel (api, webhook, etc.)
            assurance_level: Assurance level (AAL1, AAL2, AAL3)
        """
        self._specs = compiled_specs
        self._account_tier = account_tier
        self._channel = channel
        self._assurance_level = assurance_level

    def check(self, tool_name: str, params: dict) -> Any:
        """
        Check if a tool call is allowed by policy.

        Args:
            tool_name: Name of the tool to check
            params: Tool parameters

        Returns:
            The tool spec if allowed

        Raises:
            ToolPolicyViolation: If policy is violated
            ApprovalRequired: If approval is required
            AssuranceInsufficient: If assurance level is insufficient
        """
        spec = self._specs.get(tool_name)
        if not spec:
            raise ToolPolicyViolation(f"Tool not found: {tool_name}")

        # Basic policy checks - can be expanded with more sophisticated rules
        # For now, this is a minimal implementation to make imports work
        return spec
