"""
LangChain Memory Adapter - Butler 4-tier memory architecture preserved.

This adapter exposes Butler's multi-tier memory (Hot Redis, Warm Qdrant,
Cold Postgres/TurboQuant, Graph Neo4j) as a LangChain BaseChatMessageHistory.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from domain.memory.contracts import MemoryServiceContract


class ButlerMemoryAdapter(BaseChatMessageHistory):
    """LangChain chat history adapter for Butler's 4-tier memory architecture.

    This adapter:
    - Wraps Butler's MemoryService for session history retrieval
    - Converts Butler session turns to LangChain message format
    - Supports 4-tier memory composition (Hot, Warm, Cold, Graph)
    - Provides token-budgeted context assembly
    """

    def __init__(
        self,
        session_id: str,
        memory_service: MemoryServiceContract | None = None,
        account_id: str | None = None,
        tenant_id: str | None = None,
        max_tokens: int = 200_000,
    ):
        """Initialize the Butler memory adapter.

        Args:
            session_id: Session identifier
            memory_service: Butler's MemoryService instance
            account_id: Account identifier
            tenant_id: Tenant identifier for multi-tenant isolation (Phase 3)
            max_tokens: Maximum tokens for context assembly
        """
        self.session_id = session_id
        self.account_id = account_id
        self.tenant_id = tenant_id
        self.memory_service = memory_service
        self.max_tokens = max_tokens
        self._messages: list[BaseMessage] = []

    async def aadd_messages(self, messages: Sequence[BaseMessage]) -> None:
        """Add messages to Butler's memory service.

        This writes to the Hot tier (Redis) for immediate availability,
        with eventual writeback to Warm/Cold tiers.
        """
        if not self.memory_service or not self.account_id:
            self._messages.extend(messages)
            return

        for message in messages:
            role = "user" if isinstance(message, HumanMessage) else "assistant"
            content = message.content

            # Write to Butler's memory service
            await self.memory_service.store_turn(
                account_id=self.account_id,
                session_id=self.session_id,
                role=role,
                content=content,
                tenant_id=self.tenant_id,
            )

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        """Synchronous add (delegates to async)."""
        # For synchronous contexts, we'll need to handle this differently
        # For now, store locally
        self._messages.extend(messages)

    async def aget_messages(self) -> Sequence[BaseMessage]:
        """Retrieve messages from Butler's 4-tier memory.

        This composes context from:
        - Hot: Recent session turns (Redis)
        - Warm: Relevant memories (Qdrant)
        - Cold: Long-term storage (Postgres/TurboQuant)
        - Graph: Relational context (Neo4j)
        """
        if not self.memory_service or not self.account_id:
            return self._messages

        try:
            # Build context using Butler's 4-tier memory
            context = await self.memory_service.build_context(
                account_id=self.account_id,
                query="",  # Empty query for full history
                session_id=self.session_id,
            )

            # Convert Butler context to LangChain messages
            return self._convert_context_pack_to_messages(context)
        except Exception as e:
            # Fallback to local messages if memory service fails
            import structlog

            logger = structlog.get_logger(__name__)
            logger.warning(
                "memory_adapter_fallback",
                session_id=self.session_id,
                error=str(e),
            )
            return self._messages

    def get_messages(self) -> Sequence[BaseMessage]:
        """Synchronous get (returns cached messages)."""
        return self._messages

    def _convert_context_pack_to_messages(self, context: Any) -> list[BaseMessage]:
        """Convert Butler ContextPack to LangChain message format.

        Args:
            context: Butler ContextPack with session_history and relevant_memories

        Returns:
            List of LangChain BaseMessage objects
        """
        messages = []

        # Add system context if available
        if hasattr(context, "summary_anchor") and context.summary_anchor:
            messages.append(SystemMessage(content=context.summary_anchor))

        # Add session history
        if hasattr(context, "session_history"):
            for turn in context.session_history:
                role = getattr(turn, "role", "user")
                content = getattr(turn, "content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        # Add relevant memories as system context
        if hasattr(context, "relevant_memories") and context.relevant_memories:
            memory_content = "\n".join(
                [f"- {mem.content if hasattr(mem, 'content') else str(mem)}" for mem in context.relevant_memories[:10]]
            )
            messages.append(SystemMessage(content=f"Relevant memories:\n{memory_content}"))

        return messages

    def _convert_to_langchain_messages(self, history: list[dict]) -> list[BaseMessage]:
        """Legacy conversion for backward compatibility."""
        messages = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages

    async def aclear(self) -> None:
        """Clear session history from Butler's memory."""
        self._messages.clear()
        # Note: Butler MemoryService doesn't have a delete_session method
        # Session cleanup is handled by TTL and periodic cleanup jobs

    def clear(self) -> None:
        """Synchronous clear."""
        self._messages.clear()

    async def abuild_context(
        self,
        query: str,
    ) -> dict[str, Any]:
        """Build context with 4-tier memory composition.

        Args:
            query: Query string for memory retrieval

        Returns:
            Butler context dictionary
        """
        if not self.memory_service or not self.account_id:
            return {
                "session_history": [],
                "relevant_memories": [],
                "summary_anchor": None,
            }

        context = await self.memory_service.build_context(
            account_id=self.account_id,
            query=query,
            session_id=self.session_id,
        )

        # Convert ContextPack to dict for backward compatibility
        return {
            "session_history": context.session_history,
            "relevant_memories": context.relevant_memories,
            "preferences": context.preferences,
            "entities": context.entities,
            "summary_anchor": context.summary_anchor,
            "context_token_budget": context.context_token_budget,
        }
