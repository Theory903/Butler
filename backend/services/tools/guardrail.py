"""Execution Guardrail Service - Pre-execution validation layer.

Validates tool execution requests before execution to ensure safety,
compliance, and correctness. This is the last line of defense before
actual tool execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from domain.tools.selection_contract import ToolSelection
from domain.tools.specs import ButlerToolSpec, RiskTier, ApprovalMode

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Result of guardrail validation."""

    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionGuardrail:
    """Pre-execution validation service for tool execution.

    Validates:
    - Required parameters exist
    - Values are sane (not malicious, within bounds)
    - Risk escalation handled
    - Audit log requirements met
    """

    def __init__(
        self,
        enabled: bool = True,
        strict_mode: bool = False,
        max_parameter_size: int = 10000,
        enable_schema_validation: bool = True,
    ):
        """Initialize execution guardrail.

        Args:
            enabled: Whether guardrail is enabled.
            strict_mode: If True, reject on any violation. If False, warn.
            max_parameter_size: Maximum size for parameter values (bytes).
            enable_schema_validation: Enable schema validation.
        """
        self._enabled = enabled
        self._strict_mode = strict_mode
        self._max_parameter_size = max_parameter_size
        self._enable_schema_validation = enable_schema_validation

    def validate(
        self,
        selected_tools: list[ToolSelection],
        intent_context: dict[str, Any] | None = None,
        parameters: dict[str, dict] | None = None,
        account_permissions: frozenset[str] | None = None,
    ) -> GuardrailResult:
        """Validate tool execution request.

        Args:
            selected_tools: Tools selected for execution.
            intent_context: Intent context from IntentBuilder.
            parameters: Tool parameters (tool_name -> param_dict).
            account_permissions: Account permissions for validation.

        Returns:
            GuardrailResult with validation outcome.
        """
        if not self._enabled:
            return GuardrailResult(passed=True)

        violations = []
        warnings = []
        required_approvals = []
        metadata = {"validated_tools": len(selected_tools)}

        for tool_selection in selected_tools:
            spec = tool_selection.spec
            if not spec:
                violations.append(f"Tool {tool_selection.name} missing spec")
                continue

            # Validate risk tier
            risk_violation = self._validate_risk_tier(spec, account_permissions)
            if risk_violation:
                violations.append(risk_violation)

            # Validate approval mode
            approval_req = self._validate_approval_mode(spec)
            if approval_req:
                required_approvals.append(approval_req)

            # Validate parameters if provided
            if parameters and tool_selection.name in parameters:
                tool_params = parameters[tool_selection.name]
                param_violations, param_warnings = self._validate_parameters(
                    tool_params, spec
                )
                violations.extend(param_violations)
                warnings.extend(param_warnings)

            # Check for audit requirement
            if spec.risk_tier in [RiskTier.L2, RiskTier.L3]:
                metadata["audit_required"] = True

        passed = len(violations) == 0 or (not self._strict_mode and len(violations) > 0)

        logger.info(
            "guardrail_validation_complete",
            passed=passed,
            violations=len(violations),
            warnings=len(warnings),
            required_approvals=len(required_approvals),
        )

        return GuardrailResult(
            passed=passed,
            violations=violations,
            warnings=warnings,
            required_approvals=required_approvals,
            metadata=metadata,
        )

    def _validate_risk_tier(
        self, spec: ButlerToolSpec, account_permissions: frozenset[str] | None
    ) -> str | None:
        """Validate risk tier against account permissions.

        Args:
            spec: Tool specification.
            account_permissions: Account permissions.

        Returns:
            Violation message if validation fails, None otherwise.
        """
        # L3 tools require admin approval
        if spec.risk_tier == RiskTier.L3:
            if not account_permissions or "admin" not in account_permissions:
                return f"Tool {spec.name} requires admin permissions for {spec.risk_tier.value}"

        # L2 tools with sandbox require proper permissions
        if spec.risk_tier == RiskTier.L2 and spec.sandbox_required:
            if not account_permissions:
                return f"Tool {spec.name} requires account permissions for sandboxed execution"

        return None

    def _validate_approval_mode(self, spec: ButlerToolSpec) -> str | None:
        """Validate approval mode and return approval requirement.

        Args:
            spec: Tool specification.

        Returns:
            Approval requirement string if needed, None otherwise.
        """
        if spec.approval_mode == ApprovalMode.REQUIRED:
            return f"Tool {spec.name} requires explicit approval"
        elif spec.approval_mode == ApprovalMode.OPTIONAL:
            return f"Tool {spec.name} requires optional approval based on policy"
        elif spec.approval_mode == ApprovalMode.HUMAN_IN_LOOP:
            return f"Tool {spec.name} requires human approval for each use"
        return None

    def _validate_parameters(
        self, parameters: dict[str, Any], spec: ButlerToolSpec
    ) -> tuple[list[str], list[str]]:
        """Validate tool parameters.

        Args:
            parameters: Tool parameters.
            spec: Tool specification with schema.

        Returns:
            Tuple of (violations, warnings).
        """
        violations = []
        warnings = []

        if not self._enable_schema_validation:
            return violations, warnings

        # Check required parameters
        required_fields = spec.input_schema.get("required", [])
        for field in required_fields:
            if field not in parameters:
                violations.append(f"Missing required parameter: {field}")

        # Check parameter sizes
        for key, value in parameters.items():
            if isinstance(value, str):
                if len(value.encode("utf-8")) > self._max_parameter_size:
                    violations.append(
                        f"Parameter {key} exceeds maximum size ({self._max_parameter_size} bytes)"
                    )

            # Check for potential injection patterns
            if isinstance(value, str):
                injection_patterns = [
                    r"<script[^>]*>.*?</script>",  # XSS
                    r";.*drop\s+table",  # SQL injection
                    r"\${.*}",  # Template injection
                ]
                for pattern in injection_patterns:
                    if re.search(pattern, value, re.IGNORECASE):
                        warnings.append(
                            f"Parameter {key} contains potentially dangerous pattern"
                        )

        # Check parameter types against schema
        properties = spec.input_schema.get("properties", {})
        for key, value in parameters.items():
            if key in properties:
                prop_schema = properties[key]
                expected_type = prop_schema.get("type")

                if expected_type == "string" and not isinstance(value, str):
                    violations.append(
                        f"Parameter {key} should be string, got {type(value).__name__}"
                    )
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    violations.append(
                        f"Parameter {key} should be number, got {type(value).__name__}"
                    )
                elif expected_type == "boolean" and not isinstance(value, bool):
                    violations.append(
                        f"Parameter {key} should be boolean, got {type(value).__name__}"
                    )

        return violations, warnings
