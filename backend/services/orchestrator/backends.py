"""Butler agent backends.

Three execution strategies, one interface contract:

  ButlerDeterministicExecutor  – pre-planned tool call, zero LLM reasoning.
  HermesAgentBackend           – single-step local reasoning + optional tool.
  LangGraphAgentBackendAdapter – full multi-step graph runtime.

Select at startup via the BUTLER_AGENT_RUNTIME environment variable:
  "langgraph"  (default) → LangGraphAgentBackendAdapter
  "legacy"               → HermesAgentBackend
Any other value is treated as an invalid flag, logged as a warning, and falls
back to "langgraph".
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any, Final

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.events.schemas import ButlerEvent, StreamFinalEvent, StreamTokenEvent
from domain.ml.contracts import IReasoningRuntime, ReasoningRequest, ReasoningTier
from domain.orchestrator.runtime_kernel import ExecutionContext
from domain.tools.hermes_compiler import ButlerToolSpec

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

BUTLER_AGENT_RUNTIME: Final[str] = os.getenv("BUTLER_AGENT_RUNTIME", "langgraph").lower()
_VALID_RUNTIMES: Final[frozenset[str]] = frozenset({"langgraph", "legacy"})


# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------


class AgentDecision(BaseModel):
    """Structured single-step agent decision returned by the LLM.

    ``extra="forbid"`` ensures unexpected fields from a misbehaving model
    surface immediately rather than being silently discarded.
    """

    model_config = ConfigDict(extra="forbid")

    response: str = Field(default="")
    tool_name: str | None = None
    tool_params: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    """Immutable, normalised view of a single conversation turn."""

    role: str
    content: str


# ---------------------------------------------------------------------------
# ButlerDeterministicExecutor
# ---------------------------------------------------------------------------


class ButlerDeterministicExecutor:
    """Executes a pre-planned tool call without LLM reasoning.

    The tool to call is resolved from, in order:
      1. ``ctx.task.tool_name`` + ``ctx.task.input_data``
      2. The first non-terminal step in ``ctx.workflow.plan_schema``
    """

    def __init__(self, tools_service: Any) -> None:
        self._tools = tools_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        started_at = time.monotonic()
        action, params = self._resolve_action_and_params(ctx)

        if not action:
            logger.warning(
                "deterministic_executor_no_action",
                task_id=str(ctx.task.id),
                session_id=ctx.session_id,
            )
            return {
                "content": "No executable deterministic step was found.",
                "actions": [],
                "requires_approval": False,
                "duration_ms": _elapsed_ms(started_at),
            }

        bound = logger.bind(
            executor="deterministic",
            action=action,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )
        bound.info("deterministic_execution_start")

        spec = self._resolve_tool_spec(action)
        if spec is not None and spec.approval_mode in {"explicit", "critical"}:
            from services.orchestrator.executor import ApprovalRequired  # local to avoid circular

            raise ApprovalRequired(
                approval_type="tool_execution",
                description=(
                    f"Approve tool '{spec.name}' "
                    f"({spec.risk_tier.value}, {spec.approval_mode})"
                ),
                risk_tier=spec.risk_tier.value,
                tool_name=spec.name,
            )

        result = await self._tools.execute(
            tool_name=action,
            params=params,
            account_id=ctx.account_id,
            tenant_id=ctx.tenant_id,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )

        payload = _result_to_dict(result)
        content = _extract_content(payload)

        bound.info("deterministic_execution_complete", duration_ms=_elapsed_ms(started_at))
        return {
            "content": content,
            "actions": [payload],
            "requires_approval": False,
            "duration_ms": _elapsed_ms(started_at),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_action_and_params(
        self, ctx: ExecutionContext
    ) -> tuple[str, dict[str, Any]]:
        task_tool_name = str(getattr(ctx.task, "tool_name", "") or "").strip()
        task_input_data = getattr(ctx.task, "input_data", {})

        if task_tool_name:
            params = task_input_data if isinstance(task_input_data, dict) else {}
            return task_tool_name, params

        plan: dict[str, Any] = getattr(ctx.workflow, "plan_schema", {}) or {}
        steps: list[Any] = plan.get("steps", [])

        if not isinstance(steps, list) or not steps:
            return "", {}

        step = self._first_executable_step(steps)
        if step is None:
            return "", {}

        action = str(step.get("action", "")).strip()
        params = step.get("params", {})
        if not isinstance(params, dict):
            params = {}
        return action, params

    def _resolve_tool_spec(self, action: str) -> ButlerToolSpec | None:
        specs = getattr(self._tools, "_specs", None)
        if not isinstance(specs, dict):
            return None
        spec = specs.get(action)
        return spec if isinstance(spec, ButlerToolSpec) else None

    @staticmethod
    def _first_executable_step(
        steps: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        _terminal = frozenset({"respond", "reply", "final"})
        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action", "")).strip().lower()
            if action and action not in _terminal:
                return step
        return None


# ---------------------------------------------------------------------------
# HermesAgentBackend
# ---------------------------------------------------------------------------


class HermesAgentBackend:
    """Single-step local agent backend.

    Flow:
      1. Normalise context messages.
      2. Ask the reasoning runtime for one structured ``AgentDecision``.
      3. Optionally execute one tool.
      4. Stream the final text in fixed-size chunks, then emit a final event.
    """

    _SYSTEM_SUFFIX: Final[str] = (
        "You are Butler's local agent backend.\n"
        "You may either answer directly or call exactly one tool.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "response": "assistant reply or short explanation",\n'
        '  "tool_name": "optional tool name or null",\n'
        '  "tool_params": {}\n'
        "}\n"
        "Do not invent tool names.\n"
        "If no tool is needed, set tool_name to null."
    )

    def __init__(
        self,
        ml_runtime: IReasoningRuntime,
        tools_service: Any,
        *,
        default_tier: ReasoningTier = ReasoningTier.T2,
        stream_chunk_size: int = 64,
    ) -> None:
        if stream_chunk_size <= 0:
            raise ValueError("stream_chunk_size must be greater than 0")

        self._ml = ml_runtime
        self._tools = tools_service
        self._default_tier = default_tier
        self._stream_chunk_size = stream_chunk_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Non-streaming execution.  Drains run_streaming and returns a dict."""
        started_at = time.monotonic()
        content_parts: list[str] = []
        final_content: str | None = None

        async for event in self.run_streaming(ctx):
            if isinstance(event, StreamTokenEvent):
                token = str(event.payload.get("content", "") or "")
                if token:
                    content_parts.append(token)
            elif isinstance(event, StreamFinalEvent):
                candidate = str(event.payload.get("content", "") or "")
                if candidate:
                    final_content = candidate

        content = final_content if final_content is not None else "".join(content_parts)
        return {
            "content": content,
            "actions": [],
            "duration_ms": _elapsed_ms(started_at),
        }

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]:
        """Streaming execution — yields token events then a final event."""
        started_at = time.monotonic()
        bound = logger.bind(
            backend="hermes_agent",
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
            account_id=ctx.account_id,
            trace_id=ctx.trace_id,
        )

        messages = self._normalize_messages(getattr(ctx, "messages", []) or [])
        prompt = self._build_prompt(ctx=ctx, messages=messages)

        bound.info(
            "agent_reasoning_start",
            message_count=len(messages),
            tool_count=len(getattr(ctx, "toolset", []) or []),
            model=getattr(ctx, "model", None),
        )

        decision = await self._decide(ctx=ctx, prompt=prompt)

        final_content = decision.response.strip()
        if decision.tool_name:
            tool_output = await self._execute_tool(ctx=ctx, decision=decision)
            final_content = (
                f"{final_content}\n\n{tool_output}" if final_content else tool_output
            )

        for chunk in self._chunk_text(final_content):
            yield StreamTokenEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={"content": chunk},
            )

        yield StreamFinalEvent(
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
            payload={
                "content": final_content,
                "duration_ms": _elapsed_ms(started_at),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _decide(self, *, ctx: ExecutionContext, prompt: str) -> AgentDecision:
        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=f"{ctx.system_prompt}\n\n{self._SYSTEM_SUFFIX}",
            max_tokens=800,
            temperature=0.2,
            preferred_model=getattr(ctx, "model", None) or None,
            preferred_tier=self._default_tier,
            response_format="json",
            metadata={
                "task": "butler_agent_decision",
                "trace_id": ctx.trace_id,
                "session_id": ctx.session_id,
            },
        )

        response = await self._ml.generate(
            request,
            tenant_id=ctx.tenant_id,
            preferred_tier=self._default_tier,
        )
        return self._parse_decision(response.content)

    async def _execute_tool(
        self,
        *,
        ctx: ExecutionContext,
        decision: AgentDecision,
    ) -> str:
        tool_name = decision.tool_name
        if not tool_name:
            return ""

        logger.bind(
            backend="hermes_agent",
            tool_name=tool_name,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        ).info("agent_tool_execution_start")

        result = await self._tools.execute(
            tool_name=tool_name,
            params=decision.tool_params,
            account_id=ctx.account_id,
            tenant_id=ctx.tenant_id,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )

        payload = _result_to_dict(result)
        return _extract_content(payload)

    def _build_prompt(
        self,
        *,
        ctx: ExecutionContext,
        messages: Sequence[NormalizedMessage],
    ) -> str:
        tool_lines = [
            f"- {str(getattr(t, 'name', '')).strip()}: "
            f"{str(getattr(t, 'description', '')).strip()}"
            for t in (getattr(ctx, "toolset", []) or [])
            if str(getattr(t, "name", "")).strip()
        ]
        history_lines = [
            f"{m.role}: {m.content}" for m in messages if m.content
        ]

        return (
            "Current conversation context:\n"
            f"{chr(10).join(history_lines) or '(no messages)'}\n\n"
            "Available tools:\n"
            f"{chr(10).join(tool_lines) or '(no tools)'}"
        )

    @staticmethod
    def _normalize_messages(raw_messages: Sequence[Any]) -> list[NormalizedMessage]:
        normalized: list[NormalizedMessage] = []
        for item in raw_messages:
            if isinstance(item, dict):
                role, content = item.get("role"), item.get("content")
            else:
                role, content = getattr(item, "role", None), getattr(item, "content", None)

            role_text = str(role or "").strip() or "user"
            content_text = str(content or "").strip()
            if content_text:
                normalized.append(NormalizedMessage(role=role_text, content=content_text))
        return normalized

    @staticmethod
    def _parse_decision(raw: str) -> AgentDecision:
        text = (raw or "").strip()

        # Build a de-duped list of parse candidates, best-first.
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            c = candidate.strip()
            if c and c not in seen:
                seen.add(c)
                candidates.append(c)

        _add(text)

        # Strip markdown code fences if present.
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                _add("\n".join(lines[1:-1]))

        # Extract first JSON object as a fallback.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            _add(m.group())

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                return AgentDecision.model_validate_json(candidate)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc

        logger.warning("agent_decision_parse_failed", error=str(last_error), raw_length=len(text))
        return AgentDecision(response=text or "I'm here to help.", tool_name=None)

    def _chunk_text(self, text: str) -> list[str]:
        if not text:
            return []
        size = self._stream_chunk_size
        return [text[i : i + size] for i in range(0, len(text), size)]


# ---------------------------------------------------------------------------
# LangGraphAgentBackendAdapter
# ---------------------------------------------------------------------------


class LangGraphAgentBackendAdapter:
    """Wraps LangGraphAgentBackend with the Butler backend interface.

    The inner backend is imported lazily so the rest of the codebase is not
    broken when the optional langgraph dependencies are absent.
    """

    def __init__(
        self,
        ml_runtime: IReasoningRuntime,
        tools_service: Any,
        tool_specs: list[ButlerToolSpec] | None = None,
        tool_executor: Any | None = None,
        direct_implementations: dict[str, Any] | None = None,
        checkpoint_config: dict[str, Any] | None = None,
        default_tier: ReasoningTier = ReasoningTier.T2,
        stream_chunk_size: int = 64,
    ) -> None:
        if stream_chunk_size <= 0:
            raise ValueError("stream_chunk_size must be greater than 0")

        self._ml = ml_runtime
        self._tools = tools_service
        self._tool_specs: list[ButlerToolSpec] = tool_specs or []
        self._tool_executor = tool_executor
        self._direct_implementations: dict[str, Any] = direct_implementations or {}
        self._checkpoint_config = checkpoint_config
        self._default_tier = default_tier
        self._stream_chunk_size = stream_chunk_size

        self._backend: Any = None
        self._AgentRequest: Any = None  # set when backend is loaded

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        logger.info(
            "langgraph_adapter_run",
            task_id=str(ctx.task.id) if hasattr(ctx, "task") else None,
            session_id=ctx.session_id,
            message_count=len(getattr(ctx, "messages", [])),
        )

        request = self._build_request(ctx)
        response = await self._get_backend().run(request)

        return {
            "content": response.content or "",
            "actions": response.tool_calls or [],
            "duration_ms": (response.usage or {}).get("duration_ms", 0),
        }

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]:
        request = self._build_request(ctx)
        async for event in self._get_backend().run_streaming(request):
            yield event

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_backend(self) -> Any:
        if self._backend is not None:
            return self._backend

        try:
            from langchain.backend import AgentRequest, LangGraphAgentBackend
        except ImportError as exc:
            logger.error("langgraph_backend_import_failed", error=str(exc))
            raise RuntimeError(
                "LangGraph backend requested but dependencies are unavailable. "
                "Install langchain, langgraph, and langgraph-checkpoint-postgres."
            ) from exc

        self._AgentRequest = AgentRequest
        self._backend = LangGraphAgentBackend(
            runtime_manager=self._ml,
            tool_specs=self._tool_specs,
            tool_executor=self._tool_executor,
            direct_implementations=self._direct_implementations,
            checkpoint_config=self._checkpoint_config,
            default_tier=self._default_tier,
            stream_chunk_size=self._stream_chunk_size,
        )
        return self._backend

    def _build_request(self, ctx: ExecutionContext) -> Any:
        history = _normalize_messages_as_dicts(getattr(ctx, "messages", []) or [])

        task_input = getattr(ctx.task, "input", None) if hasattr(ctx, "task") else None
        if task_input:
            message = str(task_input)
        else:
            last_user = next(
                (m for m in reversed(history) if m.get("role") == "user"), None
            )
            message = (last_user or {}).get("content", "")

        return self._AgentRequest(
            message=message,
            tenant_id=ctx.tenant_id,
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
            user_id=getattr(ctx, "user_id", None),
            system_prompt=ctx.system_prompt,
            preferred_model=getattr(ctx, "model", None),
            preferred_tier=self._default_tier,
            conversation_history=history,
            metadata={"task_id": str(ctx.task.id)} if hasattr(ctx, "task") else {},
        )


# ---------------------------------------------------------------------------
# Module-level helpers (shared across classes)
# ---------------------------------------------------------------------------


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return dict(result.model_dump())
    if hasattr(result, "dict"):
        return dict(result.dict())
    if isinstance(result, dict):
        return dict(result)
    return {"data": result}


def _extract_content(payload: dict[str, Any]) -> str:
    """Pull the most meaningful string out of a tool result payload."""
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("content", "text", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value

    for key in ("content", "data"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return json.dumps(payload, ensure_ascii=False, default=str)


def _normalize_messages_as_dicts(raw_messages: Sequence[Any]) -> list[dict[str, Any]]:
    """Normalise messages to plain dicts (used by the LangGraph adapter)."""
    normalized: list[dict[str, Any]] = []
    for item in raw_messages:
        if isinstance(item, dict):
            role, content = item.get("role"), item.get("content")
        else:
            role, content = getattr(item, "role", None), getattr(item, "content", None)

        role_text = str(role or "").strip() or "user"
        content_text = str(content or "").strip()
        if content_text:
            normalized.append({"role": role_text, "content": content_text})
    return normalized


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_agent_backend(
    ml_runtime: Any,
    tools_service: Any,
    tool_specs: list[ButlerToolSpec],
    tool_executor: Any | None = None,
    direct_implementations: dict[str, Any] | None = None,
    checkpoint_config: dict[str, Any] | None = None,
    default_tier: ReasoningTier = ReasoningTier.T2,
    stream_chunk_size: int = 64,
) -> HermesAgentBackend | LangGraphAgentBackendAdapter:
    """Factory — selects the backend from ``BUTLER_AGENT_RUNTIME``.

    Args:
        ml_runtime:             Butler's MLRuntimeManager.
        tools_service:          Butler's tools service.
        tool_specs:             ButlerToolSpec list (LangGraph only).
        tool_executor:          ToolExecutor for L2/L3 governance (LangGraph only).
        direct_implementations: Tool name → callable mapping (LangGraph only).
        checkpoint_config:      Optional checkpoint config (LangGraph only).
        default_tier:           Default reasoning tier.
        stream_chunk_size:      Token chunk size for streaming.

    Returns:
        HermesAgentBackend | LangGraphAgentBackendAdapter
    """
    if BUTLER_AGENT_RUNTIME not in _VALID_RUNTIMES:
        logger.warning(
            "invalid_agent_backend_flag",
            flag=BUTLER_AGENT_RUNTIME,
            valid=sorted(_VALID_RUNTIMES),
            fallback="langgraph",
        )

    logger.info(
        "agent_backend_selection",
        backend=BUTLER_AGENT_RUNTIME,
        tool_specs_count=len(tool_specs),
        direct_implementations_count=len(direct_implementations or {}),
    )

    # Shared kwargs for the LangGraph adapter.
    langgraph_kwargs: dict[str, Any] = dict(
        ml_runtime=ml_runtime,
        tools_service=tools_service,
        tool_specs=tool_specs,
        tool_executor=tool_executor,
        direct_implementations=direct_implementations,
        checkpoint_config=checkpoint_config,
        default_tier=default_tier,
        stream_chunk_size=stream_chunk_size,
    )

    if BUTLER_AGENT_RUNTIME == "legacy":
        return HermesAgentBackend(
            ml_runtime=ml_runtime,
            tools_service=tools_service,
            default_tier=default_tier,
            stream_chunk_size=stream_chunk_size,
        )

    return LangGraphAgentBackendAdapter(**langgraph_kwargs)