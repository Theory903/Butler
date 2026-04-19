"""Butler Tool Executor — Phase 2.

Replaced _run_tool(asyncio.sleep mock) with ButlerToolDispatch.

What this service owns:
  - ToolExecution audit record lifecycle (PostgreSQL)
  - Idempotency check (Redis)
  - Parameter validation (jsonschema via ToolVerifier)
  - Pre/post verification dispatch
  - ButlerToolSpec lookup from compiled registry (in-memory)
  - Compensation record storage
  - ToolResult construction

What it does NOT own:
  - Approval decisions (ButlerToolPolicyGate in ButlerToolDispatch)
  - Sandbox execution (HermesEnvBridge + handle_function_call in ButlerToolDispatch)
  - Memory writes (MemoryWritePolicy — caller's responsibility after receiving result)
  - Event normalization (EventNormalizer in HermesAgentBackend)
"""

from __future__ import annotations

import json
import uuid
import time
import asyncio
import structlog
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from domain.tools.models import ToolDefinition, ToolExecution
from domain.tools.contracts import ToolsServiceContract, ToolResult, ValidationResult, VerificationResult, IToolVerifier
from domain.tools.exceptions import ToolErrors
from domain.tools.hermes_compiler import ButlerToolSpec, HermesToolCompiler
from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge

logger = structlog.get_logger(__name__)


class ToolExecutor(ToolsServiceContract):
    """Sandboxed, audited tool execution with Butler-owned spec registry.

    Injected into DurableExecutor and OrchestratorService.
    All physical dispatching goes through ButlerToolDispatch.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        verifier: IToolVerifier,           # accepts any IToolVerifier impl
        compiled_specs: dict[str, ButlerToolSpec] | None = None,
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
    ):
        self._db = db
        self._redis = redis
        self._verifier = verifier

        # Compiled ButlerToolSpecs — primary source of truth
        # If not injected (startup/test), compile on-demand
        self._specs: dict[str, ButlerToolSpec] = compiled_specs or {}
        self._env_bridge = HermesEnvBridge()
        self._dispatcher = ButlerToolDispatch(
            compiled_specs=self._specs,
            env_bridge=self._env_bridge,
            account_tier=account_tier,
            channel=channel,
            assurance_level=assurance_level,
        )

    # ── Public: execute ───────────────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        params: dict,
        account_id: str,
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
        """
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

        # 2. Idempotency check
        if idempotency_key:
            cached = await self._check_idempotent(idempotency_key)
            if cached:
                logger.info("tool_idempotent_cache_hit", tool_name=tool_name, key=idempotency_key)
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
            tool_name=tool_name,
            account_id=uuid.UUID(account_id) if account_id else uuid.uuid4(),
            task_id=uuid.UUID(task_id) if task_id else None,
            input_params=self._redact_params_for_audit(params, spec),
            risk_tier=spec.risk_tier.value,
            status="executing",
            idempotency_key=idempotency_key,
        )
        self._db.add(execution)
        await self._db.flush()

        start_ms = int(time.monotonic() * 1000)

        # 6. Dispatch
        try:
            butler_result = await asyncio.wait_for(
                self._dispatcher.dispatch(
                    tool_name=tool_name,
                    params=params,
                    task_id=task_id,
                    session_id=session_id,
                    account_id=account_id,
                    tool_call_id=tool_call_id or str(execution.id),
                    idempotency_key=idempotency_key,
                ),
                timeout=spec.timeout_seconds,
            )
        except asyncio.TimeoutError:
            execution.status = "failed"
            execution.error_data = {"error": "timeout", "timeout_s": spec.timeout_seconds}
            execution.duration_ms = spec.timeout_seconds * 1000
            execution.completed_at = datetime.now(UTC)
            await self._db.commit()
            raise ToolErrors.timeout(tool_name, spec.timeout_seconds)

        duration_ms = int(time.monotonic() * 1000) - start_ms

        # 7. Post-execution verification
        post_check = VerificationResult(passed=True, checks=[("dispatch", butler_result.success)])
        if butler_result.success and spec.verification_mode in ("post", "both"):
            if tool_def:
                raw_result = butler_result.output or {}
                post_check = await self._verifier.verify_postconditions(tool_def, params, raw_result)

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
        if idempotency_key and butler_result.success:
            await self._cache_idempotent(idempotency_key, tool_result)

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
        _SENSITIVE = {"key", "token", "secret", "password", "credential", "auth"}
        return {
            k: "***REDACTED***" if any(s in k.lower() for s in _SENSITIVE) else v
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
            raw = await self._redis.get(f"butler:tool:idem:{key}")
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

    async def _cache_idempotent(self, key: str, result: ToolResult) -> None:
        """Cache a successful tool result for idempotency (TTL: 24 hours)."""
        try:
            await self._redis.setex(
                f"butler:tool:idem:{key}",
                86400,
                json.dumps({
                    "success": result.success,
                    "data": result.data,
                    "tool_name": result.tool_name,
                    "execution_id": result.execution_id,
                    "compensation": result.compensation,
                }),
            )
        except Exception:
            pass
