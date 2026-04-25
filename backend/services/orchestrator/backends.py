from __future__ import annotations

import json
import os
import re
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.events.schemas import ButlerEvent, StreamFinalEvent, StreamTokenEvent
from domain.ml.contracts import IReasoningRuntime, ReasoningRequest, ReasoningTier
from domain.orchestrator.runtime_kernel import ExecutionContext
from domain.tools.hermes_compiler import ButlerToolSpec

logger = structlog.get_logger(__name__)

# Feature flag for agent runtime: "legacy" (HermesAgentBackend) or "langgraph" (LangGraphAgentBackend)
BUTLER_AGENT_RUNTIME = os.getenv("BUTLER_AGENT_RUNTIME", "langgraph").lower()


class AgentDecision(BaseModel):
    """Structured single-step agent decision.

    This keeps the local Hermes bridge simple and deterministic enough to be safe,
    without dragging you back into regex soup as a life philosophy.
    """

    model_config = ConfigDict(extra="forbid")

    response: str = Field(default="")
    tool_name: str | None = None
    tool_params: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    role: str
    content: str


class ButlerDeterministicExecutor:
    """Executes a directly planned tool call without LLM reasoning."""

    def __init__(self, tools_service: Any) -> None:
        self._tools = tools_service

    async def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        started_at = time.monotonic()
        action, params = self._resolve_action_and_params(ctx)
        if not action:
            return {
                "content": "No executable deterministic step was found.",
                "actions": [],
                "duration_ms": int((time.monotonic() - started_at) * 1000),
            }

        bound_logger = logger.bind(
            executor="deterministic",
            action=action,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )
        bound_logger.info("deterministic_execution_start")

        spec = self._resolve_tool_spec(action)
        if spec is not None and spec.approval_mode in {"explicit", "critical"}:
            from services.orchestrator.executor import ApprovalRequired

            raise ApprovalRequired(
                approval_type="tool_execution",
                description=(
                    f"Approve tool '{spec.name}' ({spec.risk_tier.value}, {spec.approval_mode})"
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

        payload = self._result_to_dict(result)
        content = payload.get("data")
        if isinstance(content, dict):
            for key in ("content", "text", "message"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    content = value
                    break
        if content is None:
            content = payload.get("content")
        if content is None:
            content = json.dumps(payload, ensure_ascii=False, default=str)

        return {
            "content": str(content),
            "actions": [payload],
            "requires_approval": False,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
        }

    def _resolve_action_and_params(self, ctx: ExecutionContext) -> tuple[str, dict[str, Any]]:
        task_tool_name = str(getattr(ctx.task, "tool_name", "") or "").strip()
        task_input_data = getattr(ctx.task, "input_data", {})
        if task_tool_name:
            return task_tool_name, task_input_data if isinstance(task_input_data, dict) else {}

        plan = getattr(ctx.workflow, "plan_schema", {}) or {}
        steps = plan.get("steps", [])

        if not isinstance(steps, list) or not steps:
            return "", {}

        executable_step = self._first_executable_step(steps)
        if executable_step is None:
            return "", {}

        action = str(executable_step.get("action", "")).strip()
        params = executable_step.get("params", {})
        if not isinstance(params, dict):
            params = {}
        return action, params

    def _resolve_tool_spec(self, action: str) -> ButlerToolSpec | None:
        specs = getattr(self._tools, "_specs", None)
        if not isinstance(specs, dict):
            return None

        spec = specs.get(action)
        if isinstance(spec, ButlerToolSpec):
            return spec
        return None

    def _first_executable_step(self, steps: list[dict[str, Any]]) -> dict[str, Any] | None:
        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action", "")).strip().lower()
            if action and action not in {"respond", "reply", "final"}:
                return step
        return None

    def _result_to_dict(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        if hasattr(result, "dict"):
            return dict(result.dict())
        if isinstance(result, dict):
            return dict(result)
        return {"data": result}


class HermesAgentBackend:
    """Single-step local agent backend.

    Flow:
    1. Normalize context messages
    2. Ask reasoning runtime for one structured decision
    3. Optionally execute one tool
    4. Return final text
    """

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

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        started_at = time.monotonic()
        content_parts: list[str] = []
        final_content: str | None = None

        async for event in self.run_streaming(ctx):
            if isinstance(event, StreamTokenEvent):
                token = str(event.payload.get("content", "") or "")
                if token:
                    content_parts.append(token)
            elif isinstance(event, StreamFinalEvent):
                final_payload_content = str(event.payload.get("content", "") or "")
                if final_payload_content:
                    final_content = final_payload_content

        content = final_content if final_content is not None else "".join(content_parts)

        return {
            "content": content,
            "actions": [],
            "duration_ms": int((time.monotonic() - started_at) * 1000),
        }

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]:
        started_at = time.monotonic()
        bound_logger = logger.bind(
            backend="hermes_agent",
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
            account_id=ctx.account_id,
            trace_id=ctx.trace_id,
        )

        messages = self._normalize_messages(getattr(ctx, "messages", []) or [])
        prompt = self._build_prompt(ctx=ctx, messages=messages)

        bound_logger.info(
            "agent_reasoning_start",
            message_count=len(messages),
            tool_count=len(getattr(ctx, "toolset", []) or []),
            model=getattr(ctx, "model", None),
        )

        decision = await self._decide(ctx=ctx, prompt=prompt)

        final_content = decision.response.strip()
        if decision.tool_name:
            tool_output = await self._execute_tool_from_decision(ctx=ctx, decision=decision)
            final_content = f"{final_content}\n\n{tool_output}" if final_content else tool_output

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
                "duration_ms": int((time.monotonic() - started_at) * 1000),
            },
        )

    async def _decide(self, *, ctx: ExecutionContext, prompt: str) -> AgentDecision:
        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=(
                f"{ctx.system_prompt}\n\n"
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
            ).strip(),
            max_tokens=800,
            temperature=0.2,
            preferred_model=ctx.model if getattr(ctx, "model", None) else None,
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

    async def _execute_tool_from_decision(
        self,
        *,
        ctx: ExecutionContext,
        decision: AgentDecision,
    ) -> str:
        tool_name = decision.tool_name
        if not tool_name:
            return ""

        bound_logger = logger.bind(
            backend="hermes_agent",
            tool_name=tool_name,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )
        bound_logger.info("agent_tool_execution_start")

        result = await self._tools.execute(
            tool_name=tool_name,
            params=decision.tool_params,
            account_id=ctx.account_id,
            tenant_id=ctx.tenant_id,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )

        payload = self._result_to_dict(result)
        content = payload.get("data")
        if content is None:
            content = payload.get("content")
        if content is None:
            content = json.dumps(payload, ensure_ascii=False, default=str)

        return str(content)

    def _build_prompt(
        self,
        *,
        ctx: ExecutionContext,
        messages: Sequence[NormalizedMessage],
    ) -> str:
        tool_lines: list[str] = []
        for tool in getattr(ctx, "toolset", []) or []:
            name = str(getattr(tool, "name", "")).strip()
            description = str(getattr(tool, "description", "")).strip()
            if name:
                tool_lines.append(f"- {name}: {description}")

        history_lines = [f"{msg.role}: {msg.content}" for msg in messages if msg.content]

        return (
            "Current conversation context:\n"
            f"{chr(10).join(history_lines) if history_lines else '(no messages)'}\n\n"
            "Available tools:\n"
            f"{chr(10).join(tool_lines) if tool_lines else '(no tools)'}"
        )

    def _normalize_messages(self, raw_messages: Sequence[Any]) -> list[NormalizedMessage]:
        normalized: list[NormalizedMessage] = []

        for item in raw_messages:
            role: str | None = None
            content: str | None = None

            if isinstance(item, dict):
                role = item.get("role")
                content = item.get("content")
            else:
                role = getattr(item, "role", None)
                content = getattr(item, "content", None)

            role_text = str(role or "").strip() or "user"
            content_text = str(content or "").strip()
            if content_text:
                normalized.append(NormalizedMessage(role=role_text, content=content_text))

        return normalized

    def _parse_decision(self, raw: str) -> AgentDecision:
        text = (raw or "").strip()

        candidates: list[str] = []
        if text:
            candidates.append(text)

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                unfenced = "\n".join(lines[1:-1]).strip()
                if unfenced:
                    candidates.append(unfenced)

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidates.append(match.group())

        last_error: Exception | None = None
        seen: set[str] = set()

        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return AgentDecision.model_validate_json(candidate)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            except ValueError as exc:
                last_error = exc

        logger.warning("agent_decision_parse_failed", error=str(last_error))
        return AgentDecision(response=text or "I'm here to help.", tool_name=None, tool_params={})

    def _chunk_text(self, text: str) -> list[str]:
        if not text:
            return []
        return [
            text[i : i + self._stream_chunk_size]
            for i in range(0, len(text), self._stream_chunk_size)
        ]

    def _result_to_dict(self, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        if hasattr(result, "dict"):
            return dict(result.dict())
        if isinstance(result, dict):
            return dict(result)
        return {"data": result}


class LangGraphAgentBackendAdapter:
    """Adapter for LangGraphAgentBackend to match Butler backend interface.

    This adapter wraps LangGraphAgentBackend to provide the same interface
    as HermesAgentBackend for seamless switching via feature flag.
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
        """Initialize the LangGraph backend adapter.

        Args:
            ml_runtime: Butler's MLRuntimeManager
            tools_service: Butler's tools service
            tool_specs: List of ButlerToolSpec
            tool_executor: Butler's ToolExecutor for L2/L3 governance
            direct_implementations: Dict mapping tool name to direct implementation
            checkpoint_config: Optional checkpoint configuration
            default_tier: Default reasoning tier (matches Hermes backend)
            stream_chunk_size: Stream chunk size (matches Hermes backend)
        """
        if stream_chunk_size <= 0:
            raise ValueError("stream_chunk_size must be greater than 0")

        self._ml = ml_runtime
        self._tools = tools_service
        self._tool_specs = tool_specs or []
        self._tool_executor = tool_executor
        self._direct_implementations = direct_implementations or {}
        self._checkpoint_config = checkpoint_config
        self._default_tier = default_tier
        self._stream_chunk_size = stream_chunk_size

        # Lazy import to avoid circular dependency
        self._backend: Any = None

    def _get_backend(self) -> Any:
        """Lazy load LangGraphAgentBackend."""
        if self._backend is None:
            try:
                from langchain.backend import LangGraphAgentBackend, AgentRequest

                self._backend = LangGraphAgentBackend(
                    runtime_manager=self._ml,
                    tool_specs=self._tool_specs,
                    tool_executor=self._tool_executor,
                    direct_implementations=self._direct_implementations,
                    checkpoint_config=self._checkpoint_config,
                    default_tier=self._default_tier,
                    stream_chunk_size=self._stream_chunk_size,
                )
                self._AgentRequest = AgentRequest
            except ImportError as exc:
                logger.error("langgraph_backend_import_failed", error=str(exc))
                raise RuntimeError(
                    "LangGraph backend requested but dependencies not available. "
                    "Install langchain, langgraph, and langgraph-checkpoint-postgres."
                ) from exc
        return self._backend

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Execute agent request synchronously."""
        backend = self._get_backend()

        # Build conversation history (normalize like Hermes does)
        conversation_history = self._normalize_messages(getattr(ctx, "messages", []) or [])

        # Extract message from task
        task_input = getattr(ctx.task, "input", None) if hasattr(ctx, "task") else None
        if task_input:
            message = str(task_input)
        else:
            # Fallback to last user message
            last_user_msg = [m for m in conversation_history if m.get("role") == "user"][-1:] if conversation_history else []
            message = last_user_msg[0].get("content", "") if last_user_msg else ""

        request = self._AgentRequest(
            message=message,
            tenant_id=ctx.tenant_id,
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
            user_id=getattr(ctx, "user_id", None),
            system_prompt=ctx.system_prompt,
            preferred_model=getattr(ctx, "model", None),
            preferred_tier=self._default_tier,
            conversation_history=conversation_history,
            metadata={"task_id": str(ctx.task.id)} if hasattr(ctx, "task") else {},
        )

        response = await backend.run(request)

        return {
            "content": response.content,
            "actions": response.tool_calls or [],
            "duration_ms": response.usage.get("duration_ms", 0) if response.usage else 0,
        }

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]:
        """Execute agent request with streaming."""
        backend = self._get_backend()

        # Build conversation history (normalize like Hermes does)
        conversation_history = self._normalize_messages(getattr(ctx, "messages", []) or [])

        # Extract message from task
        task_input = getattr(ctx.task, "input", None) if hasattr(ctx, "task") else None
        if task_input:
            message = str(task_input)
        else:
            # Fallback to last user message
            last_user_msg = [m for m in conversation_history if m.get("role") == "user"][-1:] if conversation_history else []
            message = last_user_msg[0].get("content", "") if last_user_msg else ""

        request = self._AgentRequest(
            message=message,
            tenant_id=ctx.tenant_id,
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
            user_id=getattr(ctx, "user_id", None),
            system_prompt=ctx.system_prompt,
            preferred_model=getattr(ctx, "model", None),
            preferred_tier=self._default_tier,
            conversation_history=conversation_history,
            metadata={"task_id": str(ctx.task.id)} if hasattr(ctx, "task") else {},
        )

        async for event in backend.run_streaming(request):
            yield event

    def _normalize_messages(self, raw_messages: Sequence[Any]) -> list[dict[str, Any]]:
        """Normalize messages from ExecutionContext to conversation history format.

        Matches Hermes backend's _normalize_messages behavior.
        """
        normalized: list[dict[str, Any]] = []

        for item in raw_messages:
            role: str | None = None
            content: str | None = None

            if isinstance(item, dict):
                role = item.get("role")
                content = item.get("content")
            else:
                role = getattr(item, "role", None)
                content = getattr(item, "content", None)

            role_text = str(role or "").strip() or "user"
            content_text = str(content or "").strip()
            if content_text:
                normalized.append({"role": role_text, "content": content_text})

        return normalized


def create_agent_backend(
    ml_runtime: IReasoningRuntime,
    tools_service: Any,
    tool_specs: list[ButlerToolSpec] | None = None,
    tool_executor: Any | None = None,
    direct_implementations: dict[str, Any] | None = None,
    checkpoint_config: dict[str, Any] | None = None,
    default_tier: ReasoningTier = ReasoningTier.T2,
    stream_chunk_size: int = 64,
) -> Any:
    """Factory function to create agent backend based on feature flag.

    Args:
        ml_runtime: Butler's MLRuntimeManager
        tools_service: Butler's tools service
        tool_specs: List of ButlerToolSpec (for LangGraph backend)
        tool_executor: Butler's ToolExecutor (for LangGraph backend)
        direct_implementations: Dict mapping tool name to direct implementation (for LangGraph)
        checkpoint_config: Optional checkpoint configuration (for LangGraph)
        default_tier: Default reasoning tier (for both backends)
        stream_chunk_size: Stream chunk size (for both backends)

    Returns:
        Agent backend instance (HermesAgentBackend or LangGraphAgentBackendAdapter)
    """
    logger.info(
        "agent_backend_selection",
        backend=BUTLER_AGENT_RUNTIME,
    )

    if BUTLER_AGENT_RUNTIME == "langgraph":
        return LangGraphAgentBackendAdapter(
            ml_runtime=ml_runtime,
            tools_service=tools_service,
            tool_specs=tool_specs,
            tool_executor=tool_executor,
            direct_implementations=direct_implementations,
            checkpoint_config=checkpoint_config,
            default_tier=default_tier,
            stream_chunk_size=stream_chunk_size,
        )
    elif BUTLER_AGENT_RUNTIME == "legacy":
        return HermesAgentBackend(
            ml_runtime=ml_runtime,
            tools_service=tools_service,
            default_tier=default_tier,
            stream_chunk_size=stream_chunk_size,
        )
    else:
        logger.warning(
            "invalid_agent_backend_flag",
            flag=BUTLER_AGENT_RUNTIME,
            fallback="langgraph",
        )
        return LangGraphAgentBackendAdapter(
            ml_runtime=ml_runtime,
            tools_service=tools_service,
            tool_specs=tool_specs,
            tool_executor=tool_executor,
            direct_implementations=direct_implementations,
            checkpoint_config=checkpoint_config,
            default_tier=default_tier,
            stream_chunk_size=stream_chunk_size,
        )
