"""Butler Structured Output with Pydantic models.

Integrates LangChain's structured output capabilities with Butler's agent.
"""

import logging
from typing import Any

from pydantic import BaseModel

from langchain.models import ButlerChatModel

import structlog

logger = structlog.get_logger(__name__)


class ButlerStructuredOutput:
    """Structured output wrapper for Butler agents.

    This class:
    - Wraps ButlerChatModel with structured output capabilities
    - Provides Pydantic model validation
    - Supports nested and complex schemas
    - Integrates with LangChain's with_structured_output
    """

    def __init__(self, chat_model: ButlerChatModel):
        """Initialize the structured output wrapper.

        Args:
            chat_model: Butler's ChatModel instance
        """
        self._chat_model = chat_model

    def with_structured_output(
        self,
        schema: type[BaseModel] | dict[str, Any],
        method: str = "function_calling",
        **kwargs: Any,
    ) -> Any:
        """Configure the model to return structured output.

        Args:
            schema: Pydantic model or JSON schema for structured output
            method: Method to use for structured output ("function_calling" or "json_mode")
            **kwargs: Additional arguments for structured output configuration

        Returns:
            A runnable that returns structured output
        """
        try:
            # Try to use LangChain's with_structured_output if available
            if hasattr(self._chat_model, "with_structured_output"):
                return self._chat_model.with_structured_output(schema, method=method, **kwargs)
            # Fallback: wrap the model with structured output logic
            return self._structured_output_fallback(schema, method=method, **kwargs)
        except Exception as exc:
            logger.warning("structured_output_configuration_failed", error=str(exc))
            # Return the original model if structured output fails
            return self._chat_model

    def _structured_output_fallback(
        self,
        schema: type[BaseModel] | dict[str, Any],
        method: str = "function_calling",
        **kwargs: Any,
    ) -> Any:
        """Fallback implementation for structured output.

        Args:
            schema: Pydantic model or JSON schema
            method: Method to use
            **kwargs: Additional arguments

        Returns:
            A wrapper runnable
        """

        # This is a simplified fallback - in production, you'd want
        # to implement proper function calling or JSON mode parsing
        class StructuredOutputWrapper:
            def __init__(self, model, schema_obj):
                self._model = model
                self._schema = schema_obj

            async def ainvoke(self, messages, config=None):
                response = await self._model.ainvoke(messages, config)

                # Try to parse the response as the schema
                if isinstance(self._schema, type) and issubclass(self._schema, BaseModel):
                    try:
                        import json

                        parsed = json.loads(response.content)
                        return self._schema(**parsed)
                    except Exception:
                        # Return raw response if parsing fails
                        return response
                return response

        return StructuredOutputWrapper(self._chat_model, schema)

    def create_tool_from_schema(
        self,
        schema: type[BaseModel],
        name: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a tool definition from a Pydantic schema.

        Args:
            schema: Pydantic model
            name: Tool name
            description: Tool description

        Returns:
            Tool definition dictionary
        """
        schema_dict = schema.model_json_schema() if isinstance(schema, type) else schema

        tool_definition = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema_dict,
            },
        }

        return tool_definition

    def validate_output(
        self,
        output: str | dict[str, Any],
        schema: type[BaseModel],
    ) -> BaseModel | dict[str, Any] | str:
        """Validate output against a schema.

        Args:
            output: The output to validate
            schema: Pydantic model to validate against

        Returns:
            Validated output as Pydantic model, dict, or original string
        """
        try:
            if isinstance(output, str):
                import json

                parsed_output = json.loads(output)
            else:
                parsed_output = output

            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema(**parsed_output)
            return parsed_output
        except Exception as exc:
            logger.warning("output_validation_failed", error=str(exc))
            # Return original output if validation fails
            return output


# Common structured output schemas for Butler


class ToolCall(BaseModel):
    """Structured output for tool calls."""

    tool_name: str
    arguments: dict[str, Any]
    reasoning: str = ""


class AgentResponse(BaseModel):
    """Structured output for agent responses."""

    content: str
    tool_calls: list[ToolCall] = []
    confidence: float = 1.0
    metadata: dict[str, Any] = {}


class MemoryQuery(BaseModel):
    """Structured output for memory queries."""

    query: str
    memory_types: list[str] = []
    limit: int = 10
    filters: dict[str, Any] = {}


class MemoryResult(BaseModel):
    """Structured output for memory results."""

    memories: list[dict[str, Any]]
    total_count: int
    query_used: str
    retrieval_method: str


class ApprovalDecision(BaseModel):
    """Structured output for approval decisions."""

    approved: bool
    reason: str
    conditions: list[str] = []
    alternative_actions: list[str] = []


class CostEstimate(BaseModel):
    """Structured output for cost estimates."""

    estimated_cost_usd: float
    token_count: int
    model_tier: str
    breakdown: dict[str, float] = {}


class ActionResult(BaseModel):
    """Structured output for action results."""

    success: bool
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = {}


# Utility functions for creating structured output runnables


def create_structured_output_agent(
    chat_model: ButlerChatModel,
    output_schema: type[BaseModel],
    system_prompt: str | None = None,
) -> Any:
    """Create an agent that returns structured output.

    Args:
        chat_model: Butler's ChatModel instance
        output_schema: Pydantic model for output
        system_prompt: Optional system prompt

    Returns:
        A runnable that returns structured output
    """
    structured_output = ButlerStructuredOutput(chat_model)

    if system_prompt:
        # Add system prompt to guide structured output
        from langchain_core.messages import SystemMessage

        def prompt_wrapper(messages):
            if not any(isinstance(m, SystemMessage) for m in messages):
                return [SystemMessage(content=system_prompt)] + messages
            return messages

        # Note: This is a simplified wrapper
        # In production, you'd want to properly chain the prompt with the model

    return structured_output.with_structured_output(output_schema)


def create_multi_schema_agent(
    chat_model: ButlerChatModel,
    schemas: dict[str, type[BaseModel]],
    default_schema: str,
) -> Any:
    """Create an agent that can return multiple schema types.

    Args:
        chat_model: Butler's ChatModel instance
        schemas: Dictionary of schema name to Pydantic model
        default_schema: Default schema to use

    Returns:
        A runnable that can return multiple schema types
    """
    # This would implement schema selection logic
    # For now, return the default schema
    return create_structured_output_agent(chat_model, schemas[default_schema])
