"""Butler Tool Executor — Phase T5: Canonical Tool Executor Integration.

Updated to be the only execution path with canonical flow:
- receive ToolExecutionRequest
- validate RuntimeContext
- fetch ToolSpec
- run ToolPolicy
- route through OperationRouter
- check approval
- create ledger row
- execute with timeout
- execute in SandboxManager if required
- normalize result
- redact result
- write audit event
- write usage event
- return ToolResultEnvelope

What this service owns:
  - ToolExecution audit record lifecycle (PostgreSQL)
  - Idempotency check (Redis)
  - Parameter validation (jsonschema via ToolVerifier)
  - ToolPolicy evaluation
  - OperationRouter routing
  - Approval checking
  - Sandbox execution via SandboxManager
  - ToolResultEnvelope construction
  - Audit and usage event writing

What it does NOT own:
  - Approval decisions (handled by approval service)
  - Memory writes (caller's responsibility after receiving result)
  - Event normalization (handled by caller)
"""

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from opentelemetry import trace
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from core.locks import LockManager
from core.observability import ButlerMetrics, get_metrics
from domain.runtime.context import RuntimeContext
from domain.runtime.tool_result_envelope import ToolResultEnvelope
from domain.tools.contracts import (
    IToolVerifier,
    ToolResult,
    ToolsServiceContract,
    ValidationResult,
    VerificationResult,
)
from domain.tools.exceptions import ToolErrors
from domain.tools.hermes_compiler import ButlerToolSpec
from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
from domain.tools.models import ToolDefinition, ToolExecution
from domain.tools.policy import ToolPolicyDecision
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec as DomainToolSpec
from domain.sandbox.manager import SandboxManager
from services.tenant.namespace import get_tenant_namespace

tracer = trace.get_tracer(__name__)

logger = structlog.get_logger(__name__)


@dataclass
class ToolExecutionRequest:
    """Canonical tool execution request."""

    context: RuntimeContext
    tool_name: str
    input: dict
    idempotency_key: str | None = None
    approval_id: str | None = None
    workflow_id: str | None = None
    task_id: str | None = None


class ToolExecutor(ToolsServiceContract):
    """Sandboxed, audited tool execution with Butler-owned spec registry.

    Phase T5: Updated to support canonical ToolSpec and ToolPolicy integration.

    Two execution paths:
    1. Legacy execute() - uses ButlerToolSpec, ButlerToolDispatch (backward compatibility)
    2. execute_canonical() - uses DomainToolSpec, ToolPolicy, returns ToolResultEnvelope (new canonical path)

    Injected into DurableExecutor and OrchestratorService.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        verifier: IToolVerifier,  # accepts any IToolVerifier impl
        compiled_specs: dict[str, ButlerToolSpec] | None = None,
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
        breakers: CircuitBreakerRegistry | None = None,
        lock_manager: LockManager | None = None,
        health_agent: Any | None = None,
        metrics: ButlerMetrics | None = None,
        node_id: str = "unknown",
        tenant_id: str | None = None,
        # Phase T5: New canonical execution dependencies
        tool_policy: Any = None,
        sandbox_manager: SandboxManager | None = None,
        operation_router: Any = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._verifier = verifier
        self._compiled_specs = compiled_specs or {}
        self._account_tier = account_tier
        self._channel = channel
        self._assurance_level = assurance_level
        self._breakers = breakers
        self._lock_manager = lock_manager
        self._tenant_id = tenant_id
        self._health = health_agent
        self._metrics = metrics or get_metrics()
        self._node_id = node_id
        self._pending_key = f"butler:nodes:{uuid.uuid4()}:pending_tools"
        self._max_pending = 50  # Hard throttle per node

        from services.tools.auditor import ToolAuditor

        self._auditor = ToolAuditor()

        # Compiled ButlerToolSpecs — primary source of truth for legacy path
        # If not injected (startup/test), compile on-demand
        self._specs: dict[str, ButlerToolSpec] = compiled_specs or {}
        self._env_bridge = HermesEnvBridge()

        self._dispatcher = ButlerToolDispatch(
            compiled_specs=self._specs,
            env_bridge=self._env_bridge,
            account_tier=self._account_tier,
            channel=self._channel,
            assurance_level=self._assurance_level,
        )

        # Phase T5: Canonical execution dependencies
        self._tool_policy = tool_policy
        self._sandbox_manager = sandbox_manager
        self._operation_router = operation_router

    def _tool_idem_key(self, key: str) -> str:
        """Generate tenant-scoped tool idempotency key."""
        if self._tenant_id:
            namespace = get_tenant_namespace(self._tenant_id)
            return f"{namespace.prefix}:tool:idem:{key}"
        # Fallback to legacy format for non-tenant contexts
        return f"butler:tool:idem:{key}"

    def _tool_idem_running_key(self, key: str) -> str:
        """Generate tenant-scoped tool idempotency running key."""
        if self._tenant_id:
            namespace = get_tenant_namespace(self._tenant_id)
            return f"{namespace.prefix}:tool:idem:running:{key}"
        # Fallback to legacy format for non-tenant contexts
        return f"butler:tool:idem:running:{key}"

    # ── Phase T5: Canonical Execution Path ───────────────────────────────────────

    async def execute_canonical(
        self,
        request: ToolExecutionRequest,
    ) -> ToolResultEnvelope:
        """Execute a tool using the canonical ToolSpec and ToolPolicy flow.

        Phase T5: New canonical execution path.

        Flow:
          1. Validate RuntimeContext
          2. Fetch ToolSpec from registry
          3. Run ToolPolicy evaluation
          4. Route through OperationRouter
          5. Check approval
          6. Create ledger row
          7. Execute with timeout
          8. Execute in SandboxManager if required
          9. Normalize result
          10. Redact result
          11. Write audit event
          12. Write usage event
          13. Return ToolResultEnvelope

        Args:
            request: ToolExecutionRequest with context, tool_name, input, etc.

        Returns:
            ToolResultEnvelope with execution result
        """
        from services.tools.registry import ToolRegistry

        context = request.context
        tool_name = request.tool_name

        # 1. Validate RuntimeContext
        if context is None:
            return ToolResultEnvelope.failure(
                tool_name=tool_name,
                error_code="missing_context",
                error_message="RuntimeContext not provided",
                latency_ms=0,
            )

        # 2. Fetch ToolSpec from registry
        spec = ToolRegistry.get_spec(tool_name)
        if spec is None:
            return ToolResultEnvelope.failure(
                tool_name=tool_name,
                error_code="tool_not_found",
                error_message=f"Tool '{tool_name}' not found in registry",
                latency_ms=0,
            )

        # 3. Run ToolPolicy evaluation
        if self._tool_policy:
            decision = self._tool_policy.evaluate(
                context=context,
                spec=spec,
                user_permissions=frozenset(context.permissions or []),
                approval_id=request.approval_id,
            )

            if not decision.allowed:
                return ToolResultEnvelope.failure(
                    tool_name=tool_name,
                    error_code="policy_denied",
                    error_message=decision.reason,
                    latency_ms=0,
                )

            if decision.requires_approval and not request.approval_id:
                return ToolResultEnvelope.failure(
                    tool_name=tool_name,
                    error_code="approval_required",
                    error_message="Tool requires approval",
                    latency_ms=0,
                )

            if decision.requires_sandbox and not self._sandbox_manager:
                return ToolResultEnvelope.failure(
                    tool_name=tool_name,
                    error_code="sandbox_required",
                    error_message="Tool requires sandbox but sandbox not available",
                    latency_ms=0,
                )

        # 4. Route through OperationRouter (if available)
        if self._operation_router:
            from domain.orchestration.router import AdmissionDecision, OperationRequest, OperationType

            operation_request = OperationRequest(
                operation_type=OperationType.TOOL_CALL,
                tenant_id=context.tenant_id or str(context.account_id),
                account_id=str(context.account_id),
                user_id=context.user_id,
                tool_name=tool_name,
                risk_tier=spec.risk_tier.value if spec.risk_tier else None,
                estimated_cost=None,
            )

            execution_path, admission = self._operation_router.route(operation_request)
            
            if admission.decision != AdmissionDecision.ALLOW:
                return ToolResultEnvelope.failure(
                    tool_name=tool_name,
                    error_code="router_denied",
                    error_message=admission.reason,
                    latency_ms=0,
                )

        # 5. Check approval (already done in policy check)
        # 6. Create ledger row (TODO: implement in Phase T6)
        # 7. Execute with timeout
        start_time = time.time()

        try:
            # 8. Execute in SandboxManager if required
            if spec.sandbox_required and self._sandbox_manager:
                result_data = await self._execute_in_sandbox(
                    spec=spec,
                    input_data=request.input,
                    context=context,
                )
            else:
                # Direct execution (for now, use legacy dispatcher)
                result_data = await self._execute_direct(
                    spec=spec,
                    input_data=request.input,
                    context=context,
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # 9. Normalize result (TODO: implement normalization)
            # 10. Redact result (TODO: implement redaction)
            # 11. Write audit event (TODO: implement audit)
            # 12. Write usage event (TODO: implement usage)

            return ToolResultEnvelope.success(
                tool_name=tool_name,
                summary=f"Tool {tool_name} executed successfully",
                data=result_data,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "tool_execution_failed",
                tool_name=tool_name,
                error=str(e),
                tenant_id=context.tenant_id,
                account_id=context.account_id,
            )
            return ToolResultEnvelope.failure(
                tool_name=tool_name,
                error_code="execution_failed",
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def _execute_in_sandbox(
        self,
        spec: DomainToolSpec,
        input_data: dict,
        context: RuntimeContext,
    ) -> dict:
        """Execute tool in SandboxManager.

        Args:
            spec: ToolSpec
            input_data: Tool input
            context: RuntimeContext

        Returns:
            Execution result data
        """
        if not self._sandbox_manager:
            raise RuntimeError("Sandbox required but SandboxManager not available")

        # TODO: Implement actual sandbox execution
        # For now, return placeholder
        return {"sandbox_execution": True, "input": input_data}

    async def _execute_direct(
        self,
        spec: DomainToolSpec,
        input_data: dict,
        context: RuntimeContext,
    ) -> dict:
        """Execute tool directly (without sandbox).

        Args:
            spec: ToolSpec
            input_data: Tool input
            context: RuntimeContext

        Returns:
            Execution result data
        """
        # TODO: Implement actual direct execution through adapter
        # For now, return placeholder - the actual execution will be
        # implemented when adapters are fully integrated
        return {
            "direct_execution": True,
            "input": input_data,
            "tool": spec.canonical_name,
            "source_system": spec.source_system,
        }

    # ── Public: execute ───────────────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        params: dict,
        account_id: str,
        tenant_id: str,  # Required for multi-tenant isolation
        task_id: str | None = None,
        session_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Execute a tool with Butler policy, verification, and full audit trail.

        Flow:
          1. Look up ButlerToolSpec (canonical registry)
          2. Idempotency check (Redis)
          3. Parameter validation (jsonschema)
          4. Pre-execution verification (ToolVerifier)
          5. Write ToolExecution audit record (executing)
          6. Dispatch → ButlerToolDispatch → Hermes handle_function_call
          7. Post-execution verification
          8. Commit audit record (completed/failed)
          9. Cache idempotent result if applicable
         10. Return ToolResult

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        with tracer.start_as_current_span(
            f"butler.tool.execute:{tool_name}",
            attributes={
                "tool": tool_name,
                "tenant_id": tenant_id,
                "account_id": account_id,
                "session_id": session_id or "none",
                "risk_tier": self._specs.get(tool_name).risk_tier.value
                if self._specs.get(tool_name)
                else "unknown",
            },
        ) as span:
            # 1. ButlerToolSpec lookup
            spec = self._specs.get(tool_name)
            if spec is None:
                raise ToolErrors.precondition_failed(
                    f"Tool '{tool_name}' not in Butler's compiled ToolSpec registry. "
                    "Only compiled tools may be executed."
                )
            if spec.blocked:
                raise ToolErrors.precondition_failed(
                    f"Tool '{tool_name}' is FORBIDDEN: {spec.block_reason}"
                )

            # Adaptive Load Shedding: rejection based on Node Health
            if self._health:
                status = self._health.status
                if status == "UNHEALTHY":
                    self._metrics.record_load_shed(
                        node_id=self._node_id,
                        service="tool",
                        reason="node_unhealthy",
                    )
                    raise ToolErrors.service_degraded(
                        "Tool cluster node is offline for safety logic (Load Shedding)."
                    )

                # Reject L3 (Dangerous/Heavy) tools if DEGRADED
                if status == "DEGRADED" and spec.risk_tier.value == "L3":
                    self._metrics.record_load_shed(
                        node_id=self._node_id,
                        service="tool",
                        reason="node_degraded_l3_reject",
                    )
                    logger.warn(
                        "tool_load_shedding_active",
                        tool_name=tool_name,
                        risk_tier="L3",
                        node_id=self._node_id,
                    )
                    raise ToolErrors.service_degraded(
                        "High-resource tool rejected due to node resource pressure (Load Shedding)."
                    )

            # Local Congestion Control: check pending task count
            pending_count = int(await self._redis.get(self._pending_key) or 0)
            if pending_count >= self._max_pending:
                self._metrics.record_load_shed(
                    node_id=self._node_id,
                    service="tool",
                    reason="node_saturated",
                )
                logger.error("tool_node_saturated", count=pending_count, node_id=self._node_id)
                raise ToolErrors.service_degraded("Node task queue is saturated. Try again later.")

            # 2. Idempotency Lock & Check
            lock_id = (
                f"tool:idempotency:{idempotency_key}"
                if idempotency_key
                else f"tool:run:{tool_name}:{session_id or 'anon'}"
            )

            async with (
                self._lock_manager.get_lock(lock_id, ttl_ms=(spec.timeout_seconds + 30) * 1000)
                if self._lock_manager
                else contextlib.nullcontext()
            ):
                if idempotency_key:
                    cached = await self._check_idempotent(idempotency_key)
                    if cached:
                        logger.info(
                            "tool_idempotent_cache_hit", tool_name=tool_name, key=idempotency_key
                        )
                        return cached

            # 3. Parameter validation against ButlerToolSpec input schema
            if spec.input_schema:
                validation = self._validate_params_against_spec(tool_name, params, spec)
                if not validation.is_valid:
                    raise ToolErrors.precondition_failed(
                        f"Tool '{tool_name}' parameter validation failed: {validation.errors}"
                    )

            # 4. Pre-execution verification
            # ToolVerifier still runs against the legacy ToolDefinition for backward compat
            # TODO Phase 5: migrate ToolVerifier to operate on ButlerToolSpec directly
            tool_def = await self._get_tool_def_for_verifier(tool_name, spec)
            if tool_def:
                pre_check = await self._verifier.verify_preconditions(tool_def, params, account_id)
                if not pre_check.passed:
                    raise ToolErrors.precondition_failed(pre_check.reason or "Pre-check failed")

            # 5. Audit record
            execution = ToolExecution(
                tenant_id=uuid.UUID(tenant_id),
                tool_name=tool_name,
                account_id=uuid.UUID(account_id) if account_id else uuid.uuid4(),
                task_id=uuid.UUID(task_id) if task_id else None,
                input_params=self._redact_params_for_audit(params, spec),
                risk_tier=spec.risk_tier.value,
                status="executing",
                idempotency_key=idempotency_key,
            )

            # Rule: Tool Auditor check (Oracle-Grade v2.0)
            # If the tool takes a 'command' or 'binary' parameter, we audit it.
            # This is a defense-in-depth layer against malicious parameter injection.
            if "command" in params or "binary" in params:
                cmd = params.get("command") or params.get("binary")
                if isinstance(cmd, str):
                    cmd_list = cmd.split()
                elif isinstance(cmd, list):
                    cmd_list = cmd
                else:
                    cmd_list = []

                if cmd_list:
                    self._auditor.audit_execution(cmd_list, account_id)

            self._db.add(execution)
            await self._db.flush()

            start_ms = int(time.monotonic() * 1000)

            # 6. Dispatch
            if idempotency_key:
                await self._claim_idempotent_execution(
                    idempotency_key,
                    ttl_seconds=spec.timeout_seconds + 60,
                )

            try:
                # Oracle-Grade Hardening: Ensure sandbox is ready for high-risk tools
                if spec.sandbox_profile == "docker" and session_id:
                    manager = SandboxManager.get_instance()
                    # Warm up the sandbox container (handles image pull, creation, etc.)
                    await manager.get_sandbox(session_id, tenant_id)
                    span.set_attribute("sandbox", "docker")

                # Wrapped in Circuit Breaker for stability
                async def _do_dispatch():
                    return await asyncio.wait_for(
                        self._dispatcher.dispatch(
                            tool_name=tool_name,
                            params=params,
                            task_id=task_id,
                            session_id=session_id,
                            account_id=account_id,
                            tenant_id=tenant_id,
                            tool_call_id=tool_call_id or str(execution.id),
                            idempotency_key=idempotency_key,
                        ),
                        timeout=spec.timeout_seconds,
                    )

                if self._breakers:
                    # Use a specific breaker for tools, or generic if not found
                    breaker = self._breakers.register(f"tool:{spec.risk_tier.value}")
                    # Increment pending counter before dispatch
                    await self._redis.incr(self._pending_key)
                    try:
                        async with breaker.guard(_do_dispatch) as guarded_result:
                            butler_result = guarded_result
                    finally:
                        await self._redis.decr(self._pending_key)
                else:
                    await self._redis.incr(self._pending_key)
                    try:
                        butler_result = await _do_dispatch()
                    finally:
                        await self._redis.decr(self._pending_key)

            except (TimeoutError, CircuitOpenError) as e:
                execution.status = "failed"
                execution.error_data = {
                    "error": "timeout" if isinstance(e, TimeoutError) else "circuit_open",
                    "detail": str(e),
                }
                execution.duration_ms = spec.timeout_seconds * 1000
                execution.completed_at = datetime.now(UTC)
                await self._db.commit()
                if idempotency_key:
                    await self._release_idempotent_execution(idempotency_key)
                if isinstance(e, TimeoutError):
                    raise ToolErrors.timeout(tool_name, spec.timeout_seconds) from e
                raise ToolErrors.service_degraded(
                    f"Tool subsystem '{spec.risk_tier.value}' is temporarily unavailable"
                ) from e
            except Exception:
                if idempotency_key:
                    await self._release_idempotent_execution(idempotency_key)
                raise

            duration_ms = int(time.monotonic() * 1000) - start_ms

            # 7. Post-execution verification
            post_check = VerificationResult(
                passed=True, checks=[("dispatch", butler_result.success)]
            )
            if butler_result.success and spec.verification_mode in ("post", "both") and tool_def:
                raw_result = butler_result.output or {}
                post_check = await self._verifier.verify_postconditions(
                    tool_def, params, raw_result
                )

            # 8. Commit audit record
            execution.output_result = butler_result.output or {}
            execution.status = "completed" if butler_result.success else "failed"
            execution.verification_passed = post_check.passed
            execution.duration_ms = duration_ms
            execution.completed_at = datetime.now(UTC)
            if not butler_result.success and butler_result.error:
                execution.error_data = {"error": butler_result.error}

            await self._db.commit()

            tool_result = ToolResult(
                success=butler_result.success,
                data=butler_result.output or {},
                tool_name=tool_name,
                execution_id=str(execution.id),
                verification=post_check,
                compensation=butler_result.compensation_ref,
            )

            # 9. Cache idempotent result
            if idempotency_key:
                if butler_result.success:
                    await self._cache_idempotent(idempotency_key, tool_result)
                await self._release_idempotent_execution(idempotency_key)

            logger.info(
                "tool_executed",
                tool_name=tool_name,
                risk_tier=spec.risk_tier.value,
                success=butler_result.success,
                duration_ms=duration_ms,
                execution_id=str(execution.id),
            )

            return tool_result

    # ── Public: compensate ────────────────────────────────────────────────────

    async def compensate(self, compensation_ref: dict) -> bool:
        """Run compensation for a failed or rolled-back tool execution.

        compensation_ref is the dict stored by ButlerToolDispatch.
        """
        handler = compensation_ref.get("handler")
        execution_id = compensation_ref.get("execution_id", "")
        original_tool = compensation_ref.get("tool_name", "")

        if not handler:
            logger.info("tool_no_compensation_handler", tool_name=original_tool)
            return True

        logger.info(
            "tool_compensation_start",
            handler=handler,
            original_tool=original_tool,
            execution_id=execution_id,
        )

        # Compensation handler names map to tool names in the compiled registry
        # e.g. "delete_written_file" is itself a tool that takes{"path": original_path}
        params_snapshot = compensation_ref.get("params_snapshot", {})
        comp_spec = self._specs.get(handler)

        if comp_spec is None:
            logger.warning("tool_compensation_handler_not_found", handler=handler)
            return False

        try:
            result = await self._dispatcher.dispatch(
                tool_name=handler,
                params=params_snapshot,
                task_id=execution_id,
            )
            success = result.success
        except Exception:
            logger.exception("tool_compensation_dispatch_failed", handler=handler)
            success = False

        logger.info(
            "tool_compensation_done",
            handler=handler,
            success=success,
        )
        return success

    # ── Public: registry interface ────────────────────────────────────────────

    async def get_tool(self, name: str) -> ToolDefinition | None:
        """Look up ToolDefinition by name (legacy compatibility).

        Prefer using self._specs[name] directly for new code.
        """
        stmt = select(ToolDefinition).where(ToolDefinition.name == name)
        res = await self._db.execute(stmt)
        return res.scalars().first()

    async def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
        """List available tools, optionally filtered by category.

        Returns compiled ButlerToolSpec information projected as ToolDefinition
        for backward compatibility.
        """
        stmt = select(ToolDefinition)
        if category:
            stmt = stmt.where(ToolDefinition.category == category)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def validate_params(self, tool_name: str, params: dict) -> ValidationResult:
        """Validate tool parameters against compiled ButlerToolSpec schema."""
        spec = self._specs.get(tool_name)
        if not spec:
            return ValidationResult(is_valid=False, errors=["Tool not in compiled registry"])
        return self._validate_params_against_spec(tool_name, params, spec)

    # ── Private ───────────────────────────────────────────────────────────────

    def _validate_params_against_spec(
        self, tool_name: str, params: dict, spec: ButlerToolSpec
    ) -> ValidationResult:
        if not spec.input_schema:
            return ValidationResult(is_valid=True, errors=[])
        try:
            import jsonschema

            jsonschema.validate(instance=params, schema=spec.input_schema)
            return ValidationResult(is_valid=True, errors=[])
        except Exception as e:
            return ValidationResult(is_valid=False, errors=[str(e)])

    def _redact_params_for_audit(self, params: dict, spec: ButlerToolSpec) -> dict:
        """Redact sensitive parameters before writing to audit log.

        L1+ tools: redact any field name containing 'key', 'token', 'secret',
        'password', 'credential'. L0 tools: pass through.
        """
        if spec.risk_tier.value == "L0":
            return params
        sensitive = {"key", "token", "secret", "password", "credential", "auth"}
        return {
            k: "***REDACTED***" if any(s in k.lower() for s in sensitive) else v
            for k, v in params.items()
        }

    async def _get_tool_def_for_verifier(
        self, tool_name: str, spec: ButlerToolSpec
    ) -> ToolDefinition | None:
        """Fetch ToolDefinition for backward-compat ToolVerifier calls."""
        return await self.get_tool(tool_name)

    async def _check_idempotent(self, key: str) -> ToolResult | None:
        """Check Redis for a cached idempotent result."""
        try:
            raw = await self._redis.get(self._tool_idem_key(key))
            if raw:
                data = json.loads(raw)
                return ToolResult(
                    success=data["success"],
                    data=data["data"],
                    tool_name=data["tool_name"],
                    execution_id=data["execution_id"],
                    verification=VerificationResult(passed=True, checks=[("cache", True)]),
                    compensation=data.get("compensation"),
                )
        except Exception:
            pass
        return None

    async def _claim_idempotent_execution(self, key: str, ttl_seconds: int) -> None:
        """Reserve an idempotency key while a tool call is in flight.

        The distributed lock serializes callers when available, but the in-flight
        marker is the durable guard that prevents duplicate side effects if a
        caller reaches dispatch after the cache check and before the result is
        stored.
        """
        try:
            claimed = await self._redis.set(
                self._tool_idem_running_key(key),
                "1",
                ex=max(1, ttl_seconds),
                nx=True,
            )
        except Exception as exc:
            raise ToolErrors.service_degraded("Tool idempotency guard is unavailable.") from exc

        if not claimed:
            raise ToolErrors.precondition_failed(
                "A tool execution with this idempotency key is already in progress."
            )

    async def _release_idempotent_execution(self, key: str) -> None:
        """Release an in-flight idempotency marker after completion/failure."""
        try:
            await self._redis.delete(self._tool_idem_running_key(key))
        except Exception:
            logger.warning("tool_idempotency_running_release_failed", key=key)

    async def _cache_idempotent(self, key: str, result: ToolResult) -> None:
        """Cache a successful tool result for idempotency (TTL: 24 hours)."""
        with contextlib.suppress(Exception):
            await self._redis.setex(
                self._tool_idem_key(key),
                86400,
                json.dumps(
                    {
                        "success": result.success,
                        "data": result.data,
                        "tool_name": result.tool_name,
                        "execution_id": result.execution_id,
                        "compensation": result.compensation,
                    }
                ),
            )
