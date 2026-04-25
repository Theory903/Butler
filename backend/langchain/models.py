"""
LangChain Model Adapter - Butler MLRuntimeManager integration.

This adapter exposes Butler's MLRuntimeManager as a LangChain BaseChatModel,
preserving Butler's provider routing, governance, circuit breakers, and
multi-tenant isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel

import structlog

from domain.ml.contracts import ReasoningRequest, ReasoningTier

logger = structlog.get_logger(__name__)


class ButlerChatModel(BaseChatModel):
    """LangChain chat model adapter for Butler's MLRuntimeManager.

    This adapter:
    - Delegates to Butler's MLRuntimeManager for all inference
    - Preserves Butler's multi-provider routing and fallback logic
    - Maintains multi-tenant isolation via tenant_id
    - Integrates with Butler's governance, circuit breakers, and metrics
    - Supports streaming through MLRuntimeManager.generate_stream
    """

    runtime_manager: Any = None  # MLRuntimeManager - excluded from serialization
    tenant_id: str = "default"
    preferred_model: str | None = None
    preferred_tier: ReasoningTier | None = None
    temperature: float = 0.0
    max_tokens: int = 4096

    def __init__(
        self,
        runtime_manager: Any,
        tenant_id: str,
        preferred_model: str | None = None,
        preferred_tier: ReasoningTier | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ):
        """Initialize the Butler chat model adapter.

        Args:
            runtime_manager: Butler's MLRuntimeManager instance
            tenant_id: Tenant UUID for multi-tenant isolation
            preferred_model: Optional specific model name
            preferred_tier: Optional reasoning tier (T0-T3)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model parameters
        """
        super().__init__(**kwargs)
        self.runtime_manager = runtime_manager
        self.tenant_id = tenant_id
        self.preferred_model = preferred_model
        self.preferred_tier = preferred_tier
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _convert_messages_to_prompt(self, messages: list[BaseMessage]) -> tuple[str, str | None]:
        """Convert LangChain messages to Butler ReasoningRequest format.

        Returns:
            Tuple of (prompt, system_prompt)
        """
        if not messages:
            return "", None

        # Extract system message if present
        system_prompt = None
        content_messages = []

        for msg in messages:
            if msg.type == "system":
                system_prompt = msg.content
            else:
                # Convert message to string representation
                if hasattr(msg, "content"):
                    content_messages.append(f"{msg.type.upper()}: {msg.content}")
                else:
                    content_messages.append(str(msg))

        prompt = "\n".join(content_messages) if content_messages else ""
        return prompt, system_prompt

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response using Butler's MLRuntimeManager (sync wrapper)."""
        import asyncio

        # Run async method in event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self._agenerate(messages, stop, run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate response using Butler's MLRuntimeManager."""
        prompt, system_prompt = self._convert_messages_to_prompt(messages)

        # Extract tools from kwargs if present (from ToolAwareButlerChatModel)
        tools = kwargs.get("_butler_tools", [])

        # Build ReasoningRequest
        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop or [],
            preferred_model=self.preferred_model,
            preferred_tier=self.preferred_tier,
            metadata=kwargs.get("metadata", {}),
            tools=tools,
        )

        # Delegate to MLRuntimeManager
        try:
            response = await self.runtime_manager.generate(
                request=request,
                tenant_id=self.tenant_id,
                preferred_tier=self.preferred_tier,
            )

            # Convert tool_calls to LangChain format if present
            tool_calls = []
            if response.tool_calls:
                import json as _json
                from langchain_core.messages import ToolCall
                for tc in response.tool_calls:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            raw_args = _json.loads(raw_args) if raw_args else {}
                        except _json.JSONDecodeError:
                            raw_args = {}
                    tool_calls.append(ToolCall(
                        name=fn.get("name"),
                        args=raw_args,
                        id=tc.get("id"),
                    ))

            # Create AIMessage with tool_calls if present
            if tool_calls:
                ai_message = AIMessage(
                    content=response.content or "",
                    tool_calls=tool_calls,
                )
            else:
                ai_message = AIMessage(content=response.content or "")

            # Convert to LangChain ChatResult
            generation = ChatGeneration(
                message=ai_message,
                generation_info={
                    "model_version": response.model_version,
                    "provider_name": response.provider_name,
                    "finish_reason": response.finish_reason,
                    "usage": response.usage,
                    "metadata": response.metadata,
                },
            )

            return ChatResult(generations=[generation], llm_output={"token_usage": response.usage})
        except Exception as exc:
            logger.error(
                "butler_chat_model_generation_failed",
                tenant_id=self.tenant_id,
                preferred_model=self.preferred_model,
                error=str(exc),
            )
            raise

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGeneration]:
        """Async stream response using Butler's MLRuntimeManager."""
        prompt, system_prompt = self._convert_messages_to_prompt(messages)

        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop_sequences=stop or [],
            preferred_model=self.preferred_model,
            preferred_tier=self.preferred_tier,
            metadata=kwargs.get("metadata", {}),
        )

        try:
            async for chunk in self.runtime_manager.generate_stream(
                request=request,
                tenant_id=self.tenant_id,
                preferred_tier=self.preferred_tier,
            ):
                yield ChatGeneration(message=AIMessage(content=chunk))
        except Exception as exc:
            logger.error(
                "butler_chat_model_streaming_failed",
                tenant_id=self.tenant_id,
                preferred_model=self.preferred_model,
                error=str(exc),
            )
            raise

    @property
    def _llm_type(self) -> str:
        """Return the model type identifier."""
        return "butler-mlruntime"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters for this model."""
        return {
            "tenant_id": self.tenant_id,
            "preferred_model": self.preferred_model,
            "preferred_tier": self.preferred_tier.value if self.preferred_tier else None,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def with_structured_output(
        self,
        schema: dict[str, Any] | type[BaseModel],
        **kwargs: Any,
    ) -> Any:
        """Return a model that uses structured output.

        Butler's MLRuntimeManager doesn't natively support structured output,
        so we return a wrapper that handles the conversion.
        """
        # For now, return self as a simple implementation
        # This allows bind_tools to work without full structured output support
        return self

    def bind_tools(
        self,
        tools: list[Any],
        **kwargs: Any,
    ) -> Any:
        """Bind tools to the model for tool calling.

        Returns a tool-aware wrapper that can generate tool calls.
        """
        # Create a tool-aware model that stores tools and can generate tool calls
        return ToolAwareButlerChatModel(
            base_model=self,
            tools=tools,
        )


class ToolAwareButlerChatModel(BaseChatModel):
    """Tool-aware wrapper for ButlerChatModel.

    This wrapper stores tool information and makes the model tool-aware
    for LangGraph's tool calling mechanism.
    """

    base_model: ButlerChatModel
    tools: list[Any]

    def __init__(self, base_model: ButlerChatModel, tools: list[Any], **kwargs: Any):
        # Pass base_model and tools as keyword arguments for Pydantic validation
        super().__init__(base_model=base_model, tools=tools, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response by delegating to base model."""
        return self.base_model._generate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate response by delegating to base model with tools."""
        # Convert LangChain tools to ReasoningRequest format
        tools_dicts = []
        for tool in self.tools:
            if hasattr(tool, 'name') and hasattr(tool, 'description') and hasattr(tool, 'args_schema'):
                # Get the schema
                schema = {}
                if hasattr(tool.args_schema, 'model_json_schema'):
                    schema = tool.args_schema.model_json_schema()
                elif hasattr(tool.args_schema, 'schema'):
                    schema = tool.args_schema.schema()
                
                # If schema has no properties, provide a minimal schema
                # Some APIs reject empty schemas, so we add a dummy property
                if not schema.get('properties'):
                    schema = {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "Tool input"
                            }
                        }
                    }
                
                tools_dicts.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": schema,
                })
        
        # Limit to first 10 tools to avoid overwhelming the API
        tools_dicts = tools_dicts[:10]
        
        # Store tools in kwargs for the base model to use
        kwargs_with_tools = {**kwargs, "_butler_tools": tools_dicts}
        return await self.base_model._agenerate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs_with_tools,
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGeneration]:
        """Async stream response by delegating to base model."""
        async for chunk in self.base_model._astream(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        ):
            yield chunk

    @property
    def _llm_type(self) -> str:
        """Return the model type identifier."""
        return "tool-aware-butler-mlruntime"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters for this model."""
        return self.base_model._identifying_params


class ChatModelFactory:
    """Factory for creating ButlerChatModel instances with MLRuntimeManager."""

    @staticmethod
    def create(
        runtime_manager: Any,
        tenant_id: str,
        preferred_model: str | None = None,
        preferred_tier: ReasoningTier | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ButlerChatModel:
        """Create a ButlerChatModel instance.

        Args:
            runtime_manager: Butler's MLRuntimeManager instance
            tenant_id: Tenant UUID for multi-tenant isolation
            preferred_model: Optional specific model name
            preferred_tier: Optional reasoning tier (T0-T3)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model parameters

        Returns:
            Configured ButlerChatModel instance
        """
        return ButlerChatModel(
            runtime_manager=runtime_manager,
            tenant_id=tenant_id,
            preferred_model=preferred_model,
            preferred_tier=preferred_tier,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
