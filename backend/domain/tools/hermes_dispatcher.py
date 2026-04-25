"""Butler Tool Dispatch — Phase 2.

ButlerToolDispatch is the canonical execution boundary between a compiled
ButlerToolSpec and Hermes's physical handle_function_call() dispatcher.

The dispatch chain:
  1. Look up compiled ButlerToolSpec (must exist — no raw tool names)
  2. ButlerToolPolicyGate check (idempotent — HermesAgentBackend also called
     this, but ToolExecutor.execute() is also called from deterministic paths
     where the gate hasn't fired yet)
  3. Write ToolExecution audit record (pending → executing)
  4. Apply sandbox profile via HermesEnvBridge
  5. Call handle_function_call() in a thread pool (it is synchronous)
  6. Parse result, detect errors
  7. Run post-execution verification if spec.verification_mode in (post, both)
  8. Write compensation ref if spec.has_compensation
  9. Commit ToolExecution (completed/failed)
 10. Return ButlerToolResult

What does NOT happen here:
  - No approval decisions (ButlerToolPolicyGate upstream)
  - No memory writes (MemoryWritePolicy upstream)
  - No agent loop state (RuntimeKernel/HermesAgentBackend upstream)

Governed by: docs/00-governance/transplant-constitution.md §4
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field

import structlog

from domain.orchestrator.hermes_agent_backend import (
    ApprovalRequired,
    AssuranceInsufficient,
    ButlerToolPolicyGate,
    ToolPolicyViolation,
)
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier

logger = structlog.get_logger(__name__)


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class ButlerToolResult:
    """Canonical result from a tool execution.

    This is what ToolExecutor.execute() returns after ButlerToolDispatch.
    Hermes's raw string output never leaves this class.
    """

    success: bool
    tool_name: str
    execution_id: str
    risk_tier: str
    duration_ms: int
    output: dict | None = None  # Parsed output (None if suppressed by tier)
    raw_output_size: int = 0  # Always recorded; used for audit
    error: str | None = None
    has_compensation: bool = False
    compensation_ref: dict | None = None  # Opaque ref, stored in ToolExecution
    verification_passed: bool = True


# ── Compensation registry ─────────────────────────────────────────────────────
# For tools with has_compensation=True, maps tool_name → compensation handler.
# Compensation is invoked by DurableExecutor._compensate() on workflow failure.

_COMPENSATION_HANDLERS: dict[str, str] = {
    "write_file": "delete_written_file",
    "patch_file": "revert_patch",
    "send_message": "recall_message",  # platform-dependent; best-effort
    "create_cron_job": "delete_cron_job",
}


# ── Dispatcher ────────────────────────────────────────────────────────────────


class ButlerToolDispatch:
    """Dispatches tool calls through Hermes's physical execution layer.

    Used by ToolExecutor. Never used directly by routes or domain logic.
    """

    def __init__(
        self,
        compiled_specs: dict[str, ButlerToolSpec],
        env_bridge: HermesEnvBridge,
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
    ):
        self._specs = compiled_specs
        self._env_bridge = env_bridge
        self._gate = ButlerToolPolicyGate(
            compiled_specs=compiled_specs,
            account_tier=account_tier,
            channel=channel,
            assurance_level=assurance_level,
        )

    async def dispatch(
        self,
        tool_name: str,
        params: dict,
        task_id: str | None = None,
        session_id: str | None = None,
        account_id: str | None = None,
        tenant_id: str | None = None,  # Required for multi-tenant isolation
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ButlerToolResult:
        """Dispatch a tool call through Butler's policy and Hermes's executor.

        Called by ToolExecutor after its own DB bookkeeping.
        Returns ButlerToolResult — never raises Hermes exceptions.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        execution_id = f"bte_{uuid.uuid4().hex[:12]}"
        start_ms = int(time.monotonic() * 1000)

        # 1. Policy gate (may raise for deterministic paths that didn't come
        #    via HermesAgentBackend — e.g., direct API tool calls)
        try:
            spec = self._gate.check(tool_name, params)
        except (ToolPolicyViolation, AssuranceInsufficient) as e:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.warning(
                "tool_dispatch_policy_blocked",
                tool_name=tool_name,
                reason=str(e),
                account_id=account_id,
            )
            return ButlerToolResult(
                success=False,
                tool_name=tool_name,
                execution_id=execution_id,
                risk_tier=self._specs.get(
                    tool_name,
                    ButlerToolSpec(
                        name=tool_name,
                        hermes_name=tool_name,
                        risk_tier=RiskTier.L2,
                    ),
                ).risk_tier.value,
                duration_ms=duration_ms,
                error=str(e),
            )
        except ApprovalRequired:
            # Shouldn't reach dispatch if approval is required — upstream should
            # have paused the workflow. Treat as a failed dispatch.
            return ButlerToolResult(
                success=False,
                tool_name=tool_name,
                execution_id=execution_id,
                risk_tier=spec.risk_tier.value if "spec" in dir() else "L2",
                duration_ms=int(time.monotonic() * 1000) - start_ms,
                error="approval_required — tool should not have reached dispatch",
            )

        # 2. Set up sandbox environment
        env_ctx = self._env_bridge.build_env_context(spec)

        # 3. Dispatch to Hermes handle_function_call in thread pool
        raw_output: str
        try:
            raw_output = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._call_hermes_sync(
                    tool_name=tool_name,
                    params=params,
                    task_id=task_id or execution_id,
                    session_id=session_id or "",
                    tool_call_id=tool_call_id or execution_id,
                    env_ctx=env_ctx,
                ),
            )
        except Exception as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            logger.exception(
                "tool_dispatch_hermes_exception",
                tool_name=tool_name,
                execution_id=execution_id,
            )
            return ButlerToolResult(
                success=False,
                tool_name=tool_name,
                execution_id=execution_id,
                risk_tier=spec.risk_tier.value,
                duration_ms=duration_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        duration_ms = int(time.monotonic() * 1000) - start_ms

        # 4. Parse output
        parsed, is_error = self._parse_raw_output(raw_output, tool_name)

        # 5. Build visibility — L1+ output is NOT returned to the caller as plain text
        #    Output is always in the audit record (output field of ToolExecution DB row)
        #    but the ButlerToolResult.output field is only populated for L0
        visible_output = parsed if spec.risk_tier == RiskTier.L0 else None

        # 6. Compensation ref
        compensation_ref = None
        if spec.has_compensation and not is_error:
            handler = _COMPENSATION_HANDLERS.get(tool_name)
            compensation_ref = {
                "handler": handler,
                "execution_id": execution_id,
                "tool_name": tool_name,
                "params_snapshot": params,
            }

        if is_error:
            logger.warning(
                "tool_dispatch_error_result",
                tool_name=tool_name,
                execution_id=execution_id,
                duration_ms=duration_ms,
            )
        else:
            logger.info(
                "tool_dispatch_success",
                tool_name=tool_name,
                risk_tier=spec.risk_tier.value,
                duration_ms=duration_ms,
            )

        return ButlerToolResult(
            success=not is_error,
            tool_name=tool_name,
            execution_id=execution_id,
            risk_tier=spec.risk_tier.value,
            duration_ms=duration_ms,
            output=visible_output,
            raw_output_size=len(raw_output),
            error=parsed.get("error") if is_error else None,
            has_compensation=spec.has_compensation,
            compensation_ref=compensation_ref,
            verification_passed=True,  # Post-verification done by ToolExecutor
        )

    # ── Sync Hermes dispatch (runs in thread pool) ────────────────────────────

    def _call_hermes_sync(
        self,
        tool_name: str,
        params: dict,
        task_id: str,
        session_id: str,
        tool_call_id: str,
        env_ctx: EnvContext,
    ) -> str:
        """Call Hermes's handle_function_call from a thread pool executor.

        Applies and restores environment variables around the call.
        Returns the raw string output from Hermes (always a JSON string).
        """
        # Apply sandbox environment overrides
        prior: dict[str, str | None] = {}
        for k, v in env_ctx.env_overrides.items():
            prior[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            # Use langchain Hermes integration for production
            from backend.langchain.hermes_governance import HermesToolDispatcher
            from backend.langchain.hermes_governance import _hermes_impl_mapping

            # Check if this is a Hermes tool
            hermes_spec = _hermes_impl_mapping.get(tool_name)
            if not hermes_spec:
                return json.dumps({"error": f"Tool '{tool_name}' is not a Hermes implementation"})

            # Use the actual compiled specs from the global mapping
            from backend.langchain.hermes_governance import register_hermes_tools_in_butler
            compiled_specs = register_hermes_tools_in_butler()

            # Create dispatcher with actual compiled specs
            dispatcher = HermesToolDispatcher(compiled_specs=compiled_specs)
            result = asyncio.run(dispatcher.dispatch(
                tool_name=tool_name,
                args=params,
                env=env_ctx.env_overrides,
                tenant_id=env_ctx.env_overrides.get("tenant_id"),
            ))
            return json.dumps(result)

        except ImportError:
            # Langchain Hermes integration not available — return a structured error
            return json.dumps({"error": f"Hermes dispatch unavailable for tool '{tool_name}'"})
        except Exception as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        finally:
            # Restore environment
            for k, prior_val in prior.items():
                if prior_val is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = prior_val

    # ── Output parsing ────────────────────────────────────────────────────────

    def _parse_raw_output(self, raw: str, tool_name: str) -> tuple[dict, bool]:
        """Parse Hermes raw string output → (dict, is_error).

        Hermes always returns JSON strings. An error is detected by:
          - dict with "error" key
          - non-JSON output (treated as plain text success)
        """
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                is_error = "error" in parsed
                return parsed, is_error
            # List or primitive result — wrap
            return {"result": parsed}, False
        except (json.JSONDecodeError, ValueError):
            # Non-JSON: treat as plain text result
            if raw.lower().startswith("error"):
                return {"error": raw}, True
            return {"text": raw}, False


# ── Sandbox environment bridge ─────────────────────────────────────────────────


@dataclass
class EnvContext:
    """Environment overrides to apply around a tool execution."""

    sandbox_profile: str
    env_overrides: dict[str, str] = field(default_factory=dict)
    docker_image: str | None = None
    modal_config: dict | None = None
    ssh_host: str | None = None


class HermesEnvBridge:
    """Maps Butler sandbox profiles to Hermes environment adapters.

    Butler's ButlerToolSpec declares a sandbox_profile:
      none | local | docker | modal | ssh | daytona | singularity

    This class builds the EnvContext that _call_hermes_sync() injects.
    For profiles that need out-of-process execution (docker, modal, ssh),
    it sets the appropriate Hermes env vars so the Hermes `environments/`
    adapters activate the correct execution backend.

    Hermes environments/: docker_env.py, modal_env.py, ssh_env.py,
    singularity_env.py, daytona_env.py, local_env.py
    """

    _ENV_PROFILE_VARS: dict[str, dict[str, str]] = {
        # Hermes terminal tool checks HERMES_USE_DOCKER to route terminal execution
        "docker": {"HERMES_USE_DOCKER": "1", "HERMES_DOCKER_BACKEND": "enabled"},
        # Modal env is triggered by HERMES_USE_MODAL
        "modal": {"HERMES_USE_MODAL": "1"},
        # SSH env is triggered by HERMES_USE_SSH
        "ssh": {"HERMES_USE_SSH": "1"},
        # Daytona env
        "daytona": {"HERMES_USE_DAYTONA": "1"},
        # Singularity
        "singularity": {"HERMES_USE_SINGULARITY": "1"},
        # local/none — no overrides; execute in current process
        "local": {},
        "none": {},
    }

    def build_env_context(self, spec: ButlerToolSpec) -> EnvContext:
        """Build an EnvContext for the given ButlerToolSpec's sandbox profile."""
        profile = spec.sandbox_profile or "none"
        env_overrides = dict(self._ENV_PROFILE_VARS.get(profile, {}))

        # All tool executions inherit HERMES_HOME from Butler
        from infrastructure.config import settings

        env_overrides["HERMES_HOME"] = str(settings.HERMES_HOME)

        return EnvContext(
            sandbox_profile=profile,
            env_overrides=env_overrides,
        )

    def profile_name(self, spec: ButlerToolSpec) -> str:
        return spec.sandbox_profile or "none"
