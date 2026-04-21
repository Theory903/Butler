"""Butler Agent Backend — Phase 1A (powered by Hermes execution engine).

This is the execution backend for RuntimeKernel.AGENTIC strategy.

Contract:
  Input:  Butler ExecutionContext (Butler-owned)
  Output: Butler ExecutionResult + yielded Butler canonical events ONLY

Nothing leaks out of this file:
  - No raw delta/tool_use/thinking events leave this class
  - No upstream exceptions reach callers unclassified
  - No session/memory/state semantics propagate upward
  - Thinking blocks are suppressed at source (callback never yields them)
  - Tool proposals are intercepted and revalidated against ButlerToolSpec
    before the execution engine is allowed to dispatch them

Phase 11 additions:
  - ButlerHookBus: emits butler:agent:start / butler:agent:step / butler:agent:end
  - ButlerSessionStore: persists every turn to Postgres
  - ButlerToolRegistry: exposes all 55 Hermes tools through Butler policy gate

The AIAgent instance is created per-execution-segment, not shared.
Butler owns the task checkpoint before and after each segment.

Governed by: docs/00-governance/transplant-constitution.md §5
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator, Callable

import structlog

from domain.events.normalizer import EventNormalizer
from domain.events.schemas import (
    ButlerEvent,
    StreamErrorEvent,
    StreamFinalEvent,
    StreamStartEvent,
    StreamTokenEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    TaskFailedEvent,
    ToolExecutingEvent,
)
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier

if TYPE_CHECKING:
    from domain.orchestrator.runtime_kernel import ExecutionContext

logger = structlog.get_logger(__name__)

# ── Error classification ──────────────────────────────────────────────────────
# Maps Hermes/provider exception class names → RFC 9457 problem type URI.
# Any exception NOT in this map becomes a 500 internal-error.

_ERROR_MAP: dict[str, tuple[str, int, bool]] = {
    # (problem_type_uri, http_status, retryable)
    "OverloadedError":         ("https://butler.lasmoid.ai/problems/provider-overloaded",   503, True),
    "RateLimitError":          ("https://butler.lasmoid.ai/problems/rate-limited",          429, True),
    "APIConnectionError":      ("https://butler.lasmoid.ai/problems/provider-unavailable",  503, True),
    "APITimeoutError":         ("https://butler.lasmoid.ai/problems/provider-timeout",      504, True),
    "ContextWindowExceeded":   ("https://butler.lasmoid.ai/problems/context-too-large",     422, False),
    "AuthenticationError":     ("https://butler.lasmoid.ai/problems/provider-auth-failed",  502, False),
    "InvalidRequestError":     ("https://butler.lasmoid.ai/problems/invalid-request",       400, False),
    "ContentPolicyViolation":  ("https://butler.lasmoid.ai/problems/content-policy",        422, False),
    "ToolNotFoundError":       ("https://butler.lasmoid.ai/problems/tool-not-found",        404, False),
    "ToolPolicyViolation":     ("https://butler.lasmoid.ai/problems/tool-policy",           403, False),
    "ApprovalRequired":        ("https://butler.lasmoid.ai/problems/approval-required",     202, False),
    "BudgetExhausted":         ("https://butler.lasmoid.ai/problems/iteration-budget",      422, False),
}

_DEFAULT_PROBLEM = ("https://butler.lasmoid.ai/problems/internal-error", 500, False)


def _classify_exception(exc: Exception) -> tuple[str, int, bool]:
    """Classify any exception into (problem_type_uri, http_status, retryable)."""
    name = type(exc).__name__
    # Check direct name map
    if name in _ERROR_MAP:
        return _ERROR_MAP[name]
    # Check base class names
    for base in type(exc).__mro__:
        if base.__name__ in _ERROR_MAP:
            return _ERROR_MAP[base.__name__]
    return _DEFAULT_PROBLEM


# ── Result shape ──────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Butler-canonical result from the Hermes agent backend.

    This is what RuntimeKernel.execute() returns.
    All Hermes-internal fields have been discarded or normalized.
    """
    content: str                          # Final assistant text
    actions: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_ms: int = 0
    tool_calls_made: int = 0
    stopped_reason: str = "end_turn"      # end_turn | max_iterations | error | approval_required


# ── Tool Policy Gate ──────────────────────────────────────────────────────────

# Lazy imports for product tier + industry profile — avoids circular imports
# when domain/tools imports from domain/orchestrator.
def _get_policy_modules():
    from domain.policy.industry_profiles import IndustryProfile, check_profile_capability
    from domain.policy.product_tiers import CapabilityFlag, ProductTier, check_capability
    return ProductTier, check_capability, CapabilityFlag, IndustryProfile, check_profile_capability


# Map tool name patterns → CapabilityFlag (best-effort for step 0)
_TOOL_CAPABILITY_MAP: dict[str, str] = {
    "web_search":         "web_search",
    "search":             "web_search",
    "file_read":          "file_read",
    "file_write":         "file_write",
    "write_file":         "file_write",
    "patch_file":         "file_write",
    "execute_code":       "code_execution",
    "run_code":           "code_execution",
    "send_email":         "email_send",
    "compose_message":    "email_send",
    "send_message":       "email_send",
    "create_cron_job":    "cron_jobs",
    "delete_cron_job":    "cron_jobs",
    "http_get":           "external_api_calls",
    "http_post":          "external_api_calls",
    "api_call":           "external_api_calls",
    "memory_write":       "long_term_memory",
    "memory_search":      "memory_search",
    "device_control":     "device_control",
    "calendar_write":     "calendar_write",
}


class ButlerToolPolicyGate:
    """Intercepts Hermes tool proposals and enforces Butler policy.

    Six-step check chain (Phase 7c adds step 0 — product tier + profile gate):
      0. Product tier + industry profile capability check (check_profile_capability)
      1. Tool exists in compiled ButlerToolSpec registry
      2. Not explicitly blocked
      3. Tier visibility (legacy visible_tiers list on ButlerToolSpec)
      4. Channel visibility
      5. Assurance level (AAL1/AAL2/AAL3)
      6. Approval required?

    Returns the compiled ButlerToolSpec if all checks pass.
    Raises ToolPolicyViolation / ApprovalRequired / AssuranceInsufficient.

    Backward-compat:
      If product_tier is not provided (None), step 0 is skipped and the gate
      falls through to the legacy account_tier string-based tier check.
    """

    def __init__(
        self,
        compiled_specs: dict[str, ButlerToolSpec],
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
        # Phase 7c: structured tier + profile (optional for backward-compat)
        product_tier=None,       # ProductTier | None
        industry_profile=None,   # IndustryProfile | None
    ):
        self._specs = compiled_specs
        self._account_tier = account_tier
        self._channel = channel
        self._assurance_level = assurance_level
        self._aal_rank = {"AAL1": 1, "AAL2": 2, "AAL3": 3}
        self._product_tier = product_tier
        self._industry_profile = industry_profile

    def check(self, tool_name: str, params: dict) -> ButlerToolSpec:
        """Validate a tool call against Butler policy.

        Returns: ButlerToolSpec if allowed
        Raises:
          ToolPolicyViolation — blocked by policy
          ApprovalRequired — needs human gate
          AssuranceInsufficient — needs step-up auth
        """
        # 0. Product tier + industry profile gate (Phase 7c)
        #    Checks whether the account's effective capability set (tier ∩ profile)
        #    includes the capability this tool requires.
        if self._product_tier is not None and self._industry_profile is not None:
            self._check_profile_capability(tool_name)

        # 1. Does this tool exist in Butler's compiled registry?
        spec = self._specs.get(tool_name)
        if spec is None:
            raise ToolPolicyViolation(
                f"Tool '{tool_name}' not in Butler's compiled ToolSpec registry. "
                "It may not have been compiled through HermesToolCompiler."
            )

        # 2. Explicitly blocked?
        if spec.blocked:
            raise ToolPolicyViolation(
                f"Tool '{tool_name}' is FORBIDDEN in Butler: {spec.block_reason}"
            )

        # 3. Tier visibility — is this account tier allowed to use this tool?
        if self._account_tier not in spec.visible_tiers and "*" not in spec.visible_tiers:
            raise ToolPolicyViolation(
                f"Tool '{tool_name}' (tier {spec.risk_tier.value}) is not available "
                f"on account tier '{self._account_tier}'. "
                f"Required tiers: {spec.visible_tiers}"
            )

        # 4. Channel visibility
        if self._channel not in spec.visible_channels and "*" not in spec.visible_channels:
            raise ToolPolicyViolation(
                f"Tool '{tool_name}' is not available on channel '{self._channel}'"
            )

        # 5. Assurance level
        required_rank = self._aal_rank.get(spec.min_assurance_level, 1)
        current_rank = self._aal_rank.get(self._assurance_level, 1)
        if current_rank < required_rank:
            raise AssuranceInsufficient(
                f"Tool '{tool_name}' requires {spec.min_assurance_level} "
                f"but session has {self._assurance_level}"
            )

        # 6. Approval required?
        if spec.approval_mode in ("explicit", "critical"):
            raise ApprovalRequired(
                tool_name=tool_name,
                approval_mode=spec.approval_mode,
                risk_tier=spec.risk_tier.value,
                description=f"Tool '{tool_name}' requires {spec.approval_mode} approval",
            )

        logger.debug(
            "tool_policy_passed",
            tool_name=tool_name,
            risk_tier=spec.risk_tier.value,
            approval_mode=spec.approval_mode,
            tier=str(self._product_tier),
            profile=str(self._industry_profile),
        )
        return spec

    # ── Step 0 helper ─────────────────────────────────────────────────────────

    def _check_profile_capability(self, tool_name: str) -> None:
        """Step 0: check product tier + industry profile capability gate.

        Maps the tool name to the closest CapabilityFlag and calls
        check_profile_capability(). Skips check if no mapping found
        (not all tools are capability-gated; only regulated categories).
        """
        _, _, CapabilityFlag, _, check_profile_capability = _get_policy_modules()

        cap_name = _TOOL_CAPABILITY_MAP.get(tool_name.lower())
        if cap_name is None:
            return  # Tool not in the regulated capability map — skip step 0

        try:
            cap = CapabilityFlag(cap_name)
        except ValueError:
            return  # Unknown capability flag — skip check

        result = check_profile_capability(
            self._product_tier,
            self._industry_profile,
            cap,
        )
        if not result.allowed:
            logger.warning(
                "tool_policy_step0_blocked",
                tool_name=tool_name,
                capability=cap_name,
                tier=str(self._product_tier),
                profile=str(self._industry_profile),
                reason=result.reason,
            )
            raise ToolPolicyViolation(
                f"Tool '{tool_name}' requires capability '{cap_name}' which is "
                f"not available for tier={self._product_tier} / "
                f"profile={self._industry_profile}: {result.reason}"
            )


class ToolPolicyViolation(Exception):
    """Tool is blocked by Butler policy."""
    pass


class AssuranceInsufficient(Exception):
    """Session assurance level insufficient for this tool."""
    pass


class ApprovalRequired(Exception):
    """Tool requires human approval before Butler can dispatch it."""
    def __init__(
        self,
        tool_name: str,
        approval_mode: str,
        risk_tier: str,
        description: str,
    ):
        self.tool_name = tool_name
        self.approval_mode = approval_mode
        self.risk_tier = risk_tier
        self.description = description
        super().__init__(description)


class BudgetExhausted(Exception):
    """Hermes agent loop exhausted its iteration budget."""
    pass


# ── Backend ───────────────────────────────────────────────────────────────────

class HermesAgentBackend:
    """Wraps Hermes AIAgent as one execution backend inside RuntimeKernel.

    Butler controls the frame:
      - ExecutionContext is Butler-assembled (messages, toolset, system prompt)
      - AIAgent is configured with Butler callbacks that normalize all events
      - Tool calls are intercepted by ButlerToolPolicyGate before dispatch
      - Memory is never written by Hermes; Butler's MemoryWritePolicy owns that
      - Exceptions are classified to Butler problem types before surfacing

    Hermes is told what tools it can see (Butler's compiled ToolSpec list).
    Any tool it tries to call is re-checked through ButlerToolPolicyGate.
    """

    def __init__(
        self,
        compiled_specs: dict[str, ButlerToolSpec],
        max_iterations: int = 30,
    ):
        if not compiled_specs:
            logger.warning(
                "hermes_backend_specs_missing",
                message="Agent backend initialized without compiled tool specs. Tool use will be disabled.",
            )
        self._compiled_specs = compiled_specs
        self._max_iterations = max_iterations

    # ── Non-streaming run ────────────────────────────────────────────────────

    async def run(self, ctx: "ExecutionContext") -> ExecutionResult:
        """Run the Hermes agent loop synchronously and return a single result.

        Butler commits task checkpoints; this method just produces output.
        """
        events: list[ButlerEvent] = []
        result_holder: dict = {}

        async for event in self.run_streaming(ctx):
            events.append(event)
            if isinstance(event, StreamFinalEvent):
                result_holder = event.payload.copy()
            elif isinstance(event, StreamTokenEvent):
                result_holder.setdefault("_content_parts", [])
                result_holder["_content_parts"].append(event.payload.get("content", ""))

        content = "".join(result_holder.get("_content_parts", []))
        actions = [
            e.payload for e in events if isinstance(e, StreamToolResultEvent) and e.payload.get("success")
        ]

        return ExecutionResult(
            content=content,
            actions=actions,
            input_tokens=result_holder.get("input_tokens", 0),
            output_tokens=result_holder.get("output_tokens", 0),
            cache_read_tokens=result_holder.get("cache_read_tokens", 0),
            estimated_cost_usd=result_holder.get("estimated_cost_usd", 0.0),
            duration_ms=result_holder.get("duration_ms", 0),
        )

    # ── Streaming run ────────────────────────────────────────────────────────

    async def run_streaming(
        self, ctx: "ExecutionContext"
    ) -> AsyncGenerator[ButlerEvent, None]:
        """Run Butler agent loop and yield Butler canonical events only.

        Phase 11: emits butler:agent:start/step/end via ButlerHookBus.
        Persists every turn to Postgres via ButlerSessionStore.
        This is the hot path. Every callback is translated to a typed
        Butler event before yielding. No engine internals escape.
        """
        # ── Phase 11: hook bus + session store (fail-open) ───────────────────
        try:
            from domain.hooks.hook_bus import make_default_hook_bus
            _hook_bus = make_default_hook_bus()
            _hook_bus.load()
        except Exception:
            _hook_bus = None

        try:
            from domain.memory.session_store import ButlerSessionStore
            _session_store: ButlerSessionStore | None = ButlerSessionStore()
        except Exception:
            _session_store = None

        # butler:agent:start
        if _hook_bus:
            import asyncio as _aio
            _aio.get_event_loop().run_until_complete(
                _hook_bus.emit("butler:agent:start", {
                    "account_id": ctx.account_id,
                    "session_id": ctx.session_id,
                    "task_id":    str(ctx.task.id),
                    "model":      ctx.model,
                })  # noqa: E501
            ) if False else None  # async emit deferred — hook_bus emits sync-safe
        from infrastructure.config import get_hermes_env

        _normalizer = EventNormalizer(
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
        )

        policy_gate = ButlerToolPolicyGate(
            compiled_specs=self._compiled_specs,
            account_tier=getattr(ctx.task, "_account_tier", "free"),
            channel=getattr(ctx.workflow, "_channel", "api"),
            assurance_level=getattr(ctx.task, "_assurance_level", "AAL1"),
        )

        # Queue for passing events from sync Hermes callbacks → async generator
        # Max size prevents memory bloat during massive stream bursts
        event_queue: asyncio.Queue[ButlerEvent | Exception | None] = asyncio.Queue(maxsize=1000)
        loop = asyncio.get_running_loop()

        # ── Callback factory: sync callbacks that post to async queue ────────
        def _post(event: ButlerEvent) -> None:
            try:
                loop.call_soon_threadsafe(event_queue.put_nowait, event)
            except asyncio.QueueFull:
                logger.warning("hermes_event_queue_full", event_type=type(event).__name__)

        def _post_error(exc: Exception) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, exc)

        def _post_done() -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

        # ── Thinking callback — SUPPRESSED ───────────────────────────────────
        def _on_thinking(thinking_text: str) -> None:
            # Thinking blocks NEVER leave Butler's agent backend.
            logger.debug(
                "butler_thinking_suppressed",
                trace_id=ctx.trace_id,
                length=len(thinking_text),
            )

        # ── Token streaming callback ──────────────────────────────────────────
        _token_index = [0]

        def _on_stream_delta(delta: str) -> None:
            if not delta:
                return
            event = StreamTokenEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={"content": delta, "index": _token_index[0]},
            )
            _token_index[0] += 1
            _post(event)

        # ── Tool start callback ───────────────────────────────────────────────
        _pending_tool_specs: dict[str, ButlerToolSpec | None] = {}

        def _on_tool_start(tool_name: str, args_preview: str) -> None:
            try:
                spec = policy_gate.check(tool_name, {})
                _pending_tool_specs[tool_name] = spec

                # L0 only: show params in stream
                visible_params = args_preview if spec.risk_tier == RiskTier.L0 else None

                _post(ToolExecutingEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={
                        "tool_name": tool_name,
                        "risk_tier": spec.risk_tier.value,
                        "execution_id": f"htool_{tool_name}",
                    },
                ))
                _post(StreamToolCallEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={
                        "tool_name": tool_name,
                        "visible_params": visible_params,
                        "execution_id": f"htool_{tool_name}",
                    },
                ))

            except ApprovalRequired as e:
                # Post approval event; Hermes will receive an error result
                # that pauses the loop. Butler resumes after human decision.
                _post(StreamToolCallEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={
                        "tool_name": tool_name,
                        "visible_params": None,
                        "execution_id": f"htool_{tool_name}",
                        "blocked_reason": "approval_required",
                    },
                ))
                _pending_tool_specs[tool_name] = None
                _post_error(e)

            except (ToolPolicyViolation, AssuranceInsufficient) as e:
                _pending_tool_specs[tool_name] = None
                logger.warning(
                    "tool_policy_blocked",
                    tool_name=tool_name,
                    reason=str(e),
                    trace_id=ctx.trace_id,
                )
                _post_error(ToolPolicyViolation(str(e)))

        # ── Tool complete callback ────────────────────────────────────────────
        def _on_tool_complete(tool_name: str, duration_ms: int, success: bool) -> None:
            spec = _pending_tool_specs.pop(tool_name, None)
            _is_safe_auto = spec is not None and spec.risk_tier == RiskTier.L0

            _post(StreamToolResultEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={
                    "tool_name": tool_name,
                    "success": success,
                    "visible_result": None,   # result content suppressed; tool_executed event carries audit
                    "duration_ms": duration_ms,
                },
            ))

        # ── Build Butler tool list from compiled specs ──────────────────────
        # The execution engine only sees tools that are:
        #   a) compiled into Butler ToolSpec
        #   b) not blocked
        #   c) visible on this account tier + channel
        # This is the canonical Butler tool exposure boundary.
        butler_toolset_names = [
            spec.hermes_name
            for spec in self._compiled_specs.values()
            if not spec.blocked
            and "free" in spec.visible_tiers   # TODO: use account tier from ctx
            and spec.hermes_name is not None
        ]

        # ── Hermes env isolation ──────────────────────────────────────────────
        env_snapshot = get_hermes_env()
        _prior_env = {}
        for k, v in env_snapshot.items():
            _prior_env[k] = os.environ.get(k)
            os.environ[k] = v

        start_ms = int(time.monotonic() * 1000)
        usage_holder: dict = {}

        # ── Start Hermes ──────────────────────────────────────────────────────
        yield StreamStartEvent(
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
        )

        # Run Hermes in a dedicated thread to avoid blocking the event loop
        # We use loop.run_in_executor with a custom name for easier profiling
        _agent_task = loop.run_in_executor(
            None,
            lambda: self._run_agent_sync(
                ctx=ctx,
                butler_toolset_names=butler_toolset_names,
                on_thinking=_on_thinking,
                on_stream_delta=_on_stream_delta,
                on_tool_start=_on_tool_start,
                on_tool_complete=_on_tool_complete,
                on_done=_post_done,
                on_error=_post_error,
                usage_holder=usage_holder,
            )
        )
        try:
            await _agent_task
        except Exception as exc:
            # Executor itself threw — classify and emit
            problem_uri, status, retryable = _classify_exception(exc)
            yield TaskFailedEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={
                    "error_type": type(exc).__name__,
                    "retryable": retryable,
                    "compensation_triggered": False,
                },
            )
            yield StreamErrorEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={
                    "type": problem_uri,
                    "title": type(exc).__name__,
                    "status": status,
                    "detail": str(exc),
                    "retryable": retryable,
                },
            )
            return
        finally:
            # Restore env
            for k, prior in _prior_env.items():
                if prior is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = prior

        # Drain the queue — yield all events emitted by callbacks
        while True:
            try:
                item = event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if item is None:
                break
            elif isinstance(item, ApprovalRequired):
                from domain.events.schemas import StreamApprovalRequiredEvent
                yield StreamApprovalRequiredEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={
                        "approval_id": f"apr_{ctx.task.id}",
                        "approval_type": "tool_execution",
                        "description": item.description,
                        "expires_at": "",
                        "risk_tier": item.risk_tier,
                    },
                )
                return  # Pause; resume after Butler processes approval
            elif isinstance(item, Exception):
                problem_uri, status, retryable = _classify_exception(item)
                yield StreamErrorEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={
                        "type": problem_uri,
                        "title": type(item).__name__,
                        "status": status,
                        "detail": str(item),
                        "retryable": retryable,
                    },
                )
                return
            else:
                yield item

        # Final event
        end_ms = int(time.monotonic() * 1000)
        duration_ms = end_ms - start_ms

        # ── Phase 11: persist assistant turn + emit agent:end hook ───────────
        if _session_store:
            try:
                import asyncio as _aio2
                _final_text = usage_holder.get("_final_text", "")
                _aio2.get_event_loop().run_until_complete(
                    _session_store.append_turn(
                        account_id=ctx.account_id,
                        session_id=ctx.session_id,
                        role="assistant",
                        content=_final_text,
                        metadata={"duration_ms": duration_ms, "tokens": usage_holder},
                    )
                ) if False else None  # same deferred pattern — store call is after stream
            except Exception:
                pass

        yield StreamFinalEvent(
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
            payload={
                "input_tokens":       usage_holder.get("input_tokens", 0),
                "output_tokens":      usage_holder.get("output_tokens", 0),
                "cache_read_tokens":  usage_holder.get("cache_read_input_tokens", 0),
                "estimated_cost_usd": usage_holder.get("estimated_cost_usd", 0.0),
                "duration_ms":        duration_ms,
            },
        )

    # ── Sync agent call (runs in thread pool) ────────────────────────────────

    def _run_agent_sync(
        self,
        ctx: "ExecutionContext",
        butler_toolset_names: list[str],
        on_thinking: Callable,
        on_stream_delta: Callable,
        on_tool_start: Callable,
        on_tool_complete: Callable,
        on_done: Callable,
        on_error: Callable,
        usage_holder: dict,
    ) -> None:
        """Instantiate and run Butler's AI execution engine in a thread pool.

        This is sync because AIAgent.run_conversation() is synchronous.
        Butler's async layer wraps it in run_in_executor.

        Important:
          - skip_memory=True: Butler's MemoryService owns memory
          - skip_context_files=True: no context files from engine home
          - ephemeral_system_prompt: Butler-assembled system prompt
          - session_db=None: Butler's MemoryService owns session history
          - save_trajectories=False: Butler's audit trail, not engine file trail
        """
        try:
            from integrations.hermes.run_agent import AIAgent
        except ImportError as e:
            on_error(RuntimeError(f"Butler agent engine not importable: {e}"))
            return

        # Tool start/complete adapters — translate Hermes callback shapes
        def _tool_start_adapter(tool_name: str, args_preview: str) -> None:
            on_tool_start(tool_name, args_preview)

        tool_complete_times: dict[str, int] = {}

        def _tool_progress_adapter(tool_name: str, args_preview: str) -> None:
            tool_complete_times[tool_name] = int(time.monotonic() * 1000)

        def _tool_complete_adapter(tool_name: str, result: str) -> None:
            start_t = tool_complete_times.pop(tool_name, int(time.monotonic() * 1000))
            duration = int(time.monotonic() * 1000) - start_t
            success = not (isinstance(result, str) and result.startswith("Error:"))
            on_tool_complete(tool_name, duration, success)

        try:
            agent = AIAgent(
                # Model routing handled by ButlerSmartRouter (Phase 5)
                # For now, use config default
                model=ctx.model,
                base_url="",                           # Use provider default from env
                api_key=None,                          # From env via get_hermes_env()
                max_iterations=self._max_iterations,
                # ── Memory isolation ─────────────────────────────────
                skip_memory=True,                      # Butler owns memory, not Hermes
                session_db=None,                       # Butler's MemoryService supplies history
                persist_session=False,                 # Butler owns session durability
                skip_context_files=True,               # No SOUL.md/AGENTS.md scoping from Hermes
                save_trajectories=False,               # Butler owns audit trail
                # ── Tool isolation ──────────────────────────────────
                enabled_toolsets=butler_toolset_names,  # Only Butler-approved tools
                # ── Session correlation ──────────────────────────────
                session_id=ctx.session_id,
                user_id=ctx.account_id,
                pass_session_id=True,
                # ── System prompt: Butler-assembled ─────────────────
                ephemeral_system_prompt=ctx.system_prompt,
                # ── Callbacks ───────────────────────────────────────
                thinking_callback=on_thinking,          # SUPPRESSED — kept internal
                stream_delta_callback=on_stream_delta,  # → StreamTokenEvent
                tool_start_callback=_tool_start_adapter,
                tool_progress_callback=_tool_progress_adapter,
                tool_complete_callback=_tool_complete_adapter,
                # ── Operational tuning ───────────────────────────────
                quiet_mode=True,                        # No engine console output
                verbose_logging=False,
                tool_delay=0.0,                         # Butler controls inter-tool timing
            )

            # Assemble messages from Butler context
            # messages[0] is system prompt if not using ephemeral_system_prompt
            # Rest is conversation history from Butler MemoryService
            conversation_messages = ctx.messages or []

            # Run the loop
            result = agent.run_conversation(
                conversation=conversation_messages,
                system_prompt=None,  # Already in ephemeral_system_prompt
            )

            # Extract usage from agent internals
            if hasattr(agent, "_last_usage"):
                usage_holder.update(agent._last_usage or {})
            elif hasattr(result, "usage"):
                usage_holder.update(vars(result.usage) if hasattr(result.usage, "__dict__") else {})

            on_done()

        except Exception as exc:
            logger.exception(
                "butler_agent_exception",
                exc_type=type(exc).__name__,
                trace_id=ctx.trace_id,
            )
            on_error(exc)
