"""
Tenant Entitlements - Capability-Based Access Control

Defines tenant capabilities based on plan and entitlements.
Tools, models, and features check entitlements before execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Plan(StrEnum):
    """Subscription plans."""

    FREE = "free"
    PRO = "pro"
    OPERATOR = "operator"
    ENTERPRISE = "enterprise"


class Entitlement(StrEnum):
    """Entitlement capabilities."""

    # Tool capabilities
    TOOL_CODE_EXECUTION = "tool:code_execution"
    TOOL_TERMINAL = "tool:terminal"
    TOOL_BROWSER = "tool:browser"
    TOOL_FILE_READ = "tool:file_read"
    TOOL_FILE_WRITE = "tool:file_write"
    TOOL_WEB_SEARCH = "tool:web_search"

    # Model capabilities
    MODEL_GPT_4 = "model:gpt-4"
    MODEL_CLAUDE_OPUS = "model:claude-opus"
    MODEL_CLAUDE_SONNET = "model:claude-sonnet"
    MODEL_GEMINI_PRO = "model:gemini-pro"

    # Feature capabilities
    FEATURE_LONG_CONTEXT = "feature:long_context"
    FEATURE_STREAMING = "feature:streaming"
    FEATURE_FUNCTION_CALLING = "feature:function_calling"
    FEATURE_MULTI_MODAL = "feature:multi_modal"

    # Rate limit capabilities
    RATE_LIMIT_HIGH = "rate_limit:high"
    RATE_LIMIT_UNLIMITED = "rate_limit:unlimited"


@dataclass(frozen=True, slots=True)
class EntitlementPolicy:
    """
    Tenant entitlement policy.

    Defines what a tenant can access based on plan and custom entitlements.
    Checked by ToolExecutor, MLRuntime, and other services before execution.
    """

    plan: Plan
    entitlements: frozenset[Entitlement]

    def has_entitlement(self, entitlement: Entitlement) -> bool:
        """Check if tenant has specific entitlement."""
        return entitlement in self.entitlements

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if tenant can use specific tool."""
        # Map tool names to entitlements
        tool_entitlements = {
            "code_execution": Entitlement.TOOL_CODE_EXECUTION,
            "terminal": Entitlement.TOOL_TERMINAL,
            "browser": Entitlement.TOOL_BROWSER,
            "file_read": Entitlement.TOOL_FILE_READ,
            "file_write": Entitlement.TOOL_FILE_WRITE,
            "web_search": Entitlement.TOOL_WEB_SEARCH,
        }
        entitlement = tool_entitlements.get(tool_name)
        if entitlement is None:
            return True  # Unknown tools allowed by default
        return self.has_entitlement(entitlement)

    def can_use_model(self, model_name: str) -> bool:
        """Check if tenant can use specific model."""
        # Map model names to entitlements
        model_entitlements = {
            "gpt-4": Entitlement.MODEL_GPT_4,
            "claude-opus": Entitlement.MODEL_CLAUDE_OPUS,
            "claude-sonnet": Entitlement.MODEL_CLAUDE_SONNET,
            "gemini-pro": Entitlement.MODEL_GEMINI_PRO,
        }
        entitlement = model_entitlements.get(model_name)
        if entitlement is None:
            return True  # Unknown models allowed by default
        return self.has_entitlement(entitlement)


# Default entitlement policies per plan
DEFAULT_PLAN_ENTITLEMENTS: Mapping[Plan, frozenset[Entitlement]] = {
    Plan.FREE: frozenset(
        [
            Entitlement.TOOL_WEB_SEARCH,
            Entitlement.MODEL_CLAUDE_SONNET,
            Entitlement.FEATURE_STREAMING,
        ]
    ),
    Plan.PRO: frozenset(
        [
            Entitlement.TOOL_CODE_EXECUTION,
            Entitlement.TOOL_FILE_READ,
            Entitlement.TOOL_FILE_WRITE,
            Entitlement.TOOL_WEB_SEARCH,
            Entitlement.MODEL_CLAUDE_SONNET,
            Entitlement.MODEL_GEMINI_PRO,
            Entitlement.FEATURE_STREAMING,
            Entitlement.FEATURE_FUNCTION_CALLING,
        ]
    ),
    Plan.OPERATOR: frozenset(
        [
            Entitlement.TOOL_CODE_EXECUTION,
            Entitlement.TOOL_TERMINAL,
            Entitlement.TOOL_BROWSER,
            Entitlement.TOOL_FILE_READ,
            Entitlement.TOOL_FILE_WRITE,
            Entitlement.TOOL_WEB_SEARCH,
            Entitlement.MODEL_CLAUDE_OPUS,
            Entitlement.MODEL_CLAUDE_SONNET,
            Entitlement.MODEL_GEMINI_PRO,
            Entitlement.FEATURE_LONG_CONTEXT,
            Entitlement.FEATURE_STREAMING,
            Entitlement.FEATURE_FUNCTION_CALLING,
            Entitlement.FEATURE_MULTI_MODAL,
            Entitlement.RATE_LIMIT_HIGH,
        ]
    ),
    Plan.ENTERPRISE: frozenset(
        [
            # Enterprise has all entitlements
            Entitlement.TOOL_CODE_EXECUTION,
            Entitlement.TOOL_TERMINAL,
            Entitlement.TOOL_BROWSER,
            Entitlement.TOOL_FILE_READ,
            Entitlement.TOOL_FILE_WRITE,
            Entitlement.TOOL_WEB_SEARCH,
            Entitlement.MODEL_GPT_4,
            Entitlement.MODEL_CLAUDE_OPUS,
            Entitlement.MODEL_CLAUDE_SONNET,
            Entitlement.MODEL_GEMINI_PRO,
            Entitlement.FEATURE_LONG_CONTEXT,
            Entitlement.FEATURE_STREAMING,
            Entitlement.FEATURE_FUNCTION_CALLING,
            Entitlement.FEATURE_MULTI_MODAL,
            Entitlement.RATE_LIMIT_UNLIMITED,
        ]
    ),
}


def get_default_policy(plan: str) -> EntitlementPolicy:
    """Get default entitlement policy for plan."""
    try:
        plan_enum = Plan(plan)
    except ValueError:
        plan_enum = Plan.FREE

    entitlements = DEFAULT_PLAN_ENTITLEMENTS.get(plan_enum, DEFAULT_PLAN_ENTITLEMENTS[Plan.FREE])
    return EntitlementPolicy(plan=plan_enum, entitlements=entitlements)
