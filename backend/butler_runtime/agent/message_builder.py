"""Message builder for Butler Unified Agent Runtime.

Adapted from Hermes prompt builder with Butler memory integration.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MessageBuilder:
    """Builds message sequences for model consumption.

    This class assembles messages from user input, system prompts,
    conversation history, and tool results into a format suitable for
    model consumption.
    """

    def __init__(self) -> None:
        """Initialize message builder."""

    def build_initial_message(
        self,
        user_message: str,
        system_message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Build initial message sequence for a new conversation.

        Args:
            user_message: User's input message
            system_message: Optional system prompt
            context: Optional context (account_id, session_id, etc.)

        Returns:
            List of message dictionaries
        """
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": user_message})

        return messages

    def build_with_history(
        self,
        user_message: str,
        conversation_history: list[dict[str, Any]],
        system_message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build message sequence with conversation history.

        Args:
            user_message: User's input message
            conversation_history: Previous conversation turns
            system_message: Optional system prompt
            context: Optional context (account_id, session_id, etc.)

        Returns:
            List of message dictionaries
        """
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        # Add conversation history
        for turn in conversation_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")

            if not content:
                continue

            messages.append({"role": role, "content": content})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    def build_with_memory(
        self,
        user_message: str,
        memory_context: str,
        system_message: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Build message sequence with Butler memory context.

        Args:
            user_message: User's input message
            memory_context: Context from Butler memory service
            system_message: Optional system prompt
            conversation_history: Optional conversation history

        Returns:
            List of message dictionaries
        """
        messages = []

        # Build system prompt with memory context
        if system_message:
            system_content = system_message
            if memory_context:
                system_content += f"\n\nRELEVANT CONTEXT:\n{memory_context}"
            messages.append({"role": "system", "content": system_content})
        elif memory_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"RELEVANT CONTEXT:\n{memory_context}",
                }
            )

        # Add conversation history if provided
        if conversation_history:
            for turn in conversation_history:
                role = turn.get("role", "user")
                content = turn.get("content", "")

                if not content:
                    continue

                messages.append({"role": role, "content": content})

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    def append_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        tool_call_id: str,
        result: str,
        is_error: bool = False,
    ) -> list[dict[str, Any]]:
        """Append a tool result to the message sequence.

        Args:
            messages: Existing message sequence
            tool_name: Name of the tool that was called
            tool_call_id: ID of the tool call
            result: Result from tool execution
            is_error: Whether the result is an error

        Returns:
            Updated message sequence
        """
        content = result if result else ""

        if is_error:
            content = f"Error: {content}"

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "content": content,
        }

        return messages + [tool_message]

    def append_assistant_response(
        self,
        messages: list[dict[str, Any]],
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning: str | None = None,
    ) -> list[dict[str, Any]]:
        """Append an assistant response to the message sequence.

        Args:
            messages: Existing message sequence
            content: Assistant's response content
            tool_calls: Optional tool calls made by assistant
            reasoning: Optional reasoning content (for models that support it)

        Returns:
            Updated message sequence
        """
        assistant_message = {
            "role": "assistant",
            "content": content,
        }

        if tool_calls:
            assistant_message["tool_calls"] = tool_calls

        if reasoning:
            assistant_message["reasoning"] = reasoning

        return messages + [assistant_message]

    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        char_to_token_ratio: int = 4,
    ) -> list[dict[str, Any]]:
        """Truncate message sequence to fit within token budget.

        Args:
            messages: Message sequence to truncate
            max_tokens: Maximum tokens allowed
            char_to_token_ratio: Approximate characters per token

        Returns:
            Truncated message sequence
        """
        max_chars = max_tokens * char_to_token_ratio
        total_chars = 0
        truncated_messages = []

        # Keep messages in reverse order (most recent first)
        for message in reversed(messages):
            content = message.get("content", "")
            message_chars = len(content)

            if total_chars + message_chars > max_chars and truncated_messages:
                # Truncate this message if possible
                remaining = max_chars - total_chars
                if remaining > 0:
                    message = message.copy()
                    message["content"] = content[:remaining] + "...[truncated]"
                    truncated_messages.append(message)
                break

            total_chars += message_chars
            truncated_messages.append(message.copy())

        # Reverse back to original order
        return list(reversed(truncated_messages))

    def compress_history(
        self,
        conversation_history: list[dict[str, Any]],
        max_turns: int = 10,
    ) -> list[dict[str, Any]]:
        """Compress conversation history to recent turns.

        Args:
            conversation_history: Full conversation history
            max_turns: Maximum number of turns to keep

        Returns:
            Compressed conversation history
        """
        if len(conversation_history) <= max_turns:
            return conversation_history

        # Keep the most recent turns
        return conversation_history[-max_turns:]
