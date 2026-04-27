"""Butler-Hermes memory tools.

Memory operations from Hermes that call Butler's MemoryService instead of
Hermes memory. This ensures Butler owns all memory operations.
"""

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ButlerMemoryTools:
    """Butler-native memory tools that call Butler MemoryService.

    Memory operations through Butler's unified memory system:
    - memory_search: Search memories
    - memory_store: Store a memory
    - memory_update_preference: Update user preferences
    - memory_forget: Forget a memory
    - memory_context: Get memory context for a query
    """

    def __init__(self, memory_service) -> None:
        """Initialize Butler memory tools.

        Args:
            memory_service: Butler MemoryService instance
        """
        self._memory = memory_service

    async def memory_search(
        self,
        account_id: str,
        query: str,
        limit: int = 10,
        memory_types: list[str] | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Search Butler memory for relevant memories.

        Args:
            account_id: Account ID
            query: Search query
            limit: Maximum number of results
            memory_types: Optional memory type filters
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            Dictionary with search results or error
        """
        try:
            from services.memory.retrieval import ScoredMemory

            results: list[ScoredMemory] = await self._memory.recall(
                account_id=account_id,
                query=query,
                limit=limit,
                memory_types=memory_types,
                tenant_id=tenant_id,
            )

            return {
                "account_id": account_id,
                "query": query,
                "results": [
                    {
                        "content": r.memory.content,
                        "memory_type": r.memory.memory_type,
                        "score": r.score,
                        "created_at": r.memory.created_at.isoformat()
                        if r.memory.created_at
                        else None,
                    }
                    for r in results
                ],
                "count": len(results),
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Memory search failed for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "query": query,
                "results": [],
                "error": str(e),
            }

    async def memory_store(
        self,
        account_id: str,
        content: str,
        memory_type: str = "fact",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a memory in Butler's memory system.

        Args:
            account_id: Account ID
            content: Memory content
            memory_type: Type of memory (fact, preference, etc.)
            metadata: Optional metadata

        Returns:
            Dictionary with storage result or error
        """
        try:
            stored = await self._memory.store(
                account_id=account_id,
                memory_type=memory_type,
                content=content,
                tenant_id=None,  # Will use account_id fallback
                metadata=metadata or {},
            )

            return {
                "account_id": account_id,
                "memory_id": str(stored.id) if stored else None,
                "memory_type": memory_type,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Memory store failed for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "memory_id": None,
                "memory_type": memory_type,
                "error": str(e),
            }

    async def memory_update_preference(
        self,
        account_id: str,
        key: str,
        value: str,
    ) -> dict[str, Any]:
        """Update a user preference in memory.

        Args:
            account_id: Account ID
            key: Preference key
            value: Preference value

        Returns:
            Dictionary with update result or error
        """
        try:
            content = f"{key}: {value}"

            stored = await self._memory.store(
                account_id=account_id,
                memory_type="preference",
                content=content,
                tenant_id=None,  # Will use account_id fallback
                metadata={"preference_key": key, "preference_value": value},
            )

            return {
                "account_id": account_id,
                "key": key,
                "value": value,
                "memory_id": str(stored.id) if stored else None,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Preference update failed for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "key": key,
                "value": value,
                "memory_id": None,
                "error": str(e),
            }

    async def memory_forget(
        self,
        account_id: str,
        memory_id: str | None = None,
        content_filter: str | None = None,
    ) -> dict[str, Any]:
        """Forget a memory from Butler's memory system.

        Args:
            account_id: Account ID
            memory_id: Specific memory ID to forget
            content_filter: Filter by content (if memory_id not provided)

        Returns:
            Dictionary with forget result or error
        """
        try:
            if memory_id:
                # Forget specific memory by ID
                success = await self._memory.forget(memory_id)
                return {
                    "account_id": account_id,
                    "memory_id": memory_id,
                    "forgotten": success,
                    "error": None,
                }
            if content_filter:
                # Forget memories by content filter
                count = await self._memory.forget_by_filter(
                    account_id=account_id,
                    content_filter=content_filter,
                )
                return {
                    "account_id": account_id,
                    "content_filter": content_filter,
                    "forgotten_count": count,
                    "error": None,
                }
            return {
                "account_id": account_id,
                "error": "Either memory_id or content_filter must be provided",
            }

        except Exception as e:
            logger.exception(f"Memory forget failed for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "memory_id": memory_id,
                "forgotten": False,
                "error": str(e),
            }

    async def memory_context(
        self,
        account_id: str,
        query: str,
        session_id: str | None = None,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Get memory context for a query.

        Args:
            account_id: Account ID
            query: Query string
            session_id: Optional session ID
            max_tokens: Maximum tokens for context

        Returns:
            Dictionary with memory context or error
        """
        try:
            from services.memory.context_builder import ContextPack

            context_pack: ContextPack = await self._memory.build_context(
                account_id=account_id,
                query=query,
                session_id=session_id,
                tenant_id=None,  # Will use account_id fallback
            )

            # Build context string from ContextPack components
            context_parts = []
            if context_pack.session_history:
                context_parts.append(f"Session History: {len(context_pack.session_history)} turns")
            if context_pack.relevant_memories:
                context_parts.append(
                    f"Relevant Memories: {len(context_pack.relevant_memories)} items"
                )
            if context_pack.summary_anchor:
                context_parts.append(f"Summary: {context_pack.summary_anchor}")

            context_str = "\n\n".join(context_parts)

            return {
                "account_id": account_id,
                "query": query,
                "context": context_str,
                "context_token_budget": context_pack.context_token_budget,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Memory context failed for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "query": query,
                "context": "",
                "context_token_budget": 0,
                "error": str(e),
            }
