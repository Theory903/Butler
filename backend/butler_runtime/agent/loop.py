"""Butler Unified Agent Loop.

Fuses Hermes agent-loop patterns with Butler's identity, memory, governance,
and session management. This is the core agent runtime that replaces Hermes'
standalone AIAgent with a Butler-native implementation.
"""

import logging
import time
from typing import Any

from .budget import ExecutionBudget
from .callbacks import ButlerEventSink
from .message_builder import MessageBuilder
from .tool_calling import ToolCallingHandler

import structlog

logger = structlog.get_logger(__name__)


class ButlerExecutionContext:
    """Execution context for a single agent run.

    Contains all context needed for agent execution:
    - Account and session IDs
    - User message and conversation history
    - Model selection and configuration
    - Memory context
    - Governance parameters
    """

    def __init__(
        self,
        account_id: str,
        session_id: str,
        user_message: str,
        model: str,
        conversation_history: list[dict[str, Any]] | None = None,
        system_message: str | None = None,
        memory_context: str | None = None,
        account_tier: str = "free",
        channel: str = "api",
        assurance_level: str = "AAL1",
        **kwargs: Any,
    ) -> None:
        self.account_id = account_id
        self.session_id = session_id
        self.user_message = user_message
        self.model = model
        self.conversation_history = conversation_history or []
        self.system_message = system_message
        self.memory_context = memory_context
        self.account_tier = account_tier
        self.channel = channel
        self.assurance_level = assurance_level
        self.extra = kwargs


class ButlerModelRouter:
    """Model router for Butler Unified Agent Runtime.

    Routes model requests to appropriate providers based on model selection,
    account tier, and fallback configuration.
    """

    def __init__(self) -> None:
        """Initialize model router."""

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        account_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Route chat request to appropriate model provider.

        Args:
            messages: Message sequence
            tools: Tool schemas
            model: Model identifier
            account_id: Account ID
            session_id: Session ID
            **kwargs: Additional parameters

        Returns:
            Model response with content, tool_calls, etc.

        Note: This is a stub. Real implementation will integrate with
        Butler's ML service and provider adapters.
        """
        # Stub implementation
        return {
            "content": "",
            "tool_calls": [],
            "model": model,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


class ButlerToolExecutor:
    """Tool executor for Butler Unified Agent Runtime.

    Executes tool calls through Butler's governance layer.
    """

    def __init__(self) -> None:
        """Initialize tool executor."""

    async def visible_tool_schemas(self, ctx: ButlerExecutionContext) -> list[dict[str, Any]]:
        """Get visible tool schemas for the context.

        Args:
            ctx: Execution context

        Returns:
            List of tool schemas visible to the user

        Note: This is a stub. Real implementation will integrate with
        Butler's tool registry and governance.
        """
        # Stub implementation
        return []

    async def execute_tool_call(
        self,
        ctx: ButlerExecutionContext,
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call through Butler governance.

        Args:
            ctx: Execution context
            tool_call: Tool call from model

        Returns:
            Tool execution result

        Note: This is a stub. Real implementation will integrate with
        Butler's tool executor and governance.
        """
        # Stub implementation
        tool_name = tool_call.get("function", {}).get("name", "")
        return {
            "tool_name": tool_name,
            "result": "",
            "error": None,
            "duration_ms": 0,
        }


class ButlerMemoryContextBuilder:
    """Memory context builder for Butler Unified Agent Runtime.

    Builds memory context from Butler's memory service.
    """

    def __init__(self) -> None:
        """Initialize memory context builder."""

    async def build_context(
        self,
        account_id: str,
        query: str,
        session_id: str | None = None,
    ) -> str:
        """Build memory context for the query.

        Args:
            account_id: Account ID
            query: Query string
            session_id: Optional session ID

        Returns:
            Memory context string

        Note: This is a stub. Real implementation will integrate with
        Butler's memory service and context builder.
        """
        # Stub implementation
        return ""


class ButlerUnifiedAgentLoop:
    """Butler's Unified Agent Runtime.

    Fuses Hermes agent-loop patterns with Butler's identity, memory, governance,
    and session management. This replaces Hermes' standalone AIAgent with a
    Butler-native implementation.

    The loop:
    1. Builds messages from user input, history, and memory context
    2. Calls model router for model response
    3. If tool calls present, executes through Butler tool executor
    4. Appends tool results to messages
    5. Repeats until no more tool calls or budget exhausted
    6. Returns final response

    Key differences from Hermes AIAgent:
    - Uses Butler MemoryService instead of Hermes SessionDB
    - Uses Butler ToolExecutor with governance instead of direct tool calls
    - Uses Butler ModelRouter with provider logic instead of hardcoded providers
    - Uses Butler event streaming instead of CLI-specific callbacks
    - No CLI/TUI dependencies
    - No ~/.hermes config dependencies
    """

    def __init__(
        self,
        model_router: ButlerModelRouter,
        tool_executor: ButlerToolExecutor,
        memory_context_builder: ButlerMemoryContextBuilder,
        event_sink: ButlerEventSink | None = None,
        budget: ExecutionBudget | None = None,
    ) -> None:
        """Initialize Butler Unified Agent Loop.

        Args:
            model_router: Butler model router
            tool_executor: Butler tool executor with governance
            memory_context_builder: Butler memory context builder
            event_sink: Optional event sink for streaming
            budget: Optional execution budget
        """
        self._model_router = model_router
        self._tool_executor = tool_executor
        self._memory_context_builder = memory_context_builder
        self._event_sink = event_sink or ButlerEventSink()
        self._budget = budget or ExecutionBudget()

        self._tool_calling = ToolCallingHandler()
        self._message_builder = MessageBuilder()

    async def run(self, ctx: ButlerExecutionContext) -> dict[str, Any]:
        """Run the agent loop for a single execution.

        Args:
            ctx: Execution context

        Returns:
            Execution result with final_response, messages, metadata

        Raises:
            BudgetExceededError: If execution budget is exceeded
        """
        start_time = time.monotonic()

        # Build initial messages
        if ctx.memory_context:
            messages = self._message_builder.build_with_memory(
                user_message=ctx.user_message,
                memory_context=ctx.memory_context,
                system_message=ctx.system_message,
                conversation_history=ctx.conversation_history,
            )
        elif ctx.conversation_history:
            messages = self._message_builder.build_with_history(
                user_message=ctx.user_message,
                conversation_history=ctx.conversation_history,
                system_message=ctx.system_message,
                context={
                    "account_id": ctx.account_id,
                    "session_id": ctx.session_id,
                },
            )
        else:
            messages = self._message_builder.build_initial_message(
                user_message=ctx.user_message,
                system_message=ctx.system_message,
                context={
                    "account_id": ctx.account_id,
                    "session_id": ctx.session_id,
                },
            )

        # Main agent loop
        iteration = 0
        while self._budget.can_continue():
            iteration += 1

            # Consume iteration budget
            if not self._budget.consume():
                logger.warning("Agent loop exceeded iteration budget")
                break

            # Get visible tool schemas
            tool_schemas = await self._tool_executor.visible_tool_schemas(ctx)

            # Call model
            model_response = await self._model_router.chat(
                messages=messages,
                tools=tool_schemas,
                model=ctx.model,
                account_id=ctx.account_id,
                session_id=ctx.session_id,
            )

            # Update budget with token usage
            usage = model_response.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            self._budget.consume_tokens(input_tokens, output_tokens)

            # Check for tool calls
            tool_calls = self._tool_calling.extract_tool_calls(model_response)

            if not tool_calls:
                # No tool calls - return final response
                final_response = model_response.get("content", "")
                duration_ms = int((time.monotonic() - start_time) * 1000)

                await self._event_sink.emit_complete(
                    final_response=final_response,
                    metadata={
                        "duration_ms": duration_ms,
                        "iterations": iteration,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                )

                return {
                    "final_response": final_response,
                    "messages": messages,
                    "metadata": {
                        "iterations": iteration,
                        "duration_ms": duration_ms,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "stopped_reason": "completed",
                    },
                }

            # Execute tool calls
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name", "")
                tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                tool_args = self._tool_calling.normalize_tool_args(tool_args_str, tool_name)

                await self._event_sink.emit_tool_start(tool_name, tool_args)

                try:
                    tool_start = time.monotonic()
                    tool_result = await self._tool_executor.execute_tool_call(
                        ctx=ctx, tool_call=tool_call
                    )
                    duration_ms = int((time.monotonic() - tool_start) * 1000)

                    if tool_result.get("error"):
                        await self._event_sink.emit_tool_error(
                            tool_name, tool_result["error"], duration_ms
                        )

                        # Check if we should stop on error
                        if self._tool_calling.should_stop_on_tool_error(
                            tool_name, tool_result["error"]
                        ):
                            raise Exception(f"Tool error: {tool_result['error']}")

                    await self._event_sink.emit_tool_complete(
                        tool_name,
                        tool_result.get("result", ""),
                        duration_ms,
                        metadata=tool_result.get("metadata"),
                    )

                except Exception as e:
                    logger.exception(f"Tool execution failed for {tool_name}: {e}")
                    await self._event_sink.emit_tool_error(tool_name, str(e), 0)

                    # Append error as tool result
                    messages.append(
                        self._tool_calling.to_tool_message(
                            tool_name=tool_name,
                            tool_call_id=tool_call.get("id", ""),
                            result=str(e),
                            is_error=True,
                        )
                    )
                    continue

                # Append tool result to messages
                messages.append(
                    self._tool_calling.to_tool_message(
                        tool_name=tool_name,
                        tool_call_id=tool_call.get("id", ""),
                        result=tool_result.get("result", ""),
                        is_error=tool_result.get("error") is not None,
                    )
                )

            # Append assistant response with tool calls
            messages = self._message_builder.append_assistant_response(
                messages,
                content=model_response.get("content", ""),
                tool_calls=tool_calls,
            )

        # Budget exceeded
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await self._event_sink.emit_error(
            error="Execution budget exceeded",
            metadata={"duration_ms": duration_ms, "iterations": iteration},
        )

        raise BudgetExceededError("Agent loop exceeded execution budget")


class BudgetExceededError(Exception):
    """Raised when agent execution budget is exceeded."""
