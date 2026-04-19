from abc import abstractmethod
from typing import Any, List, Optional
from pydantic import BaseModel
from domain.base import DomainService
from domain.memory.models import MemoryEntry, ConversationTurn

class ContextPack(BaseModel):
    session_history: list
    relevant_memories: list
    preferences: list
    entities: list
    context_token_budget: int

class MemoryServiceContract(DomainService):
    @abstractmethod
    async def store(self, account_id: str, memory_type: str, content: dict, **kwargs) -> MemoryEntry:
        """Store a new memory entry with embedding."""

    @abstractmethod
    async def recall(self, account_id: str, query: str, memory_types: list = None, limit: int = 10) -> list[MemoryEntry]:
        """Retrieve relevant memories using hybrid search."""

    @abstractmethod
    async def store_turn(self, account_id: str, session_id: str, role: str, content: str, **kwargs) -> ConversationTurn:
        """Store a conversation turn."""

    @abstractmethod
    async def get_session_history(self, account_id: str, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        """Get conversation history for a session."""

    @abstractmethod
    async def build_context(self, account_id: str, query: str, session_id: str) -> ContextPack:
        """Assemble full context for Orchestrator — session history + relevant memories."""

    @abstractmethod
    async def update_entity(self, account_id: str, entity_name: str, facts: dict) -> MemoryEntry:
        """Upsert entity facts with temporal versioning."""

    @abstractmethod
    async def set_preference(self, account_id: str, key: str, value: str, confidence: float) -> MemoryEntry:
        """Store or update user preference."""


# ── Infrastructure-level contracts (keep domain layer clean) ──────────────────

class IMemoryWriteStore(DomainService):
    """Abstraction over ButlerMemoryStore.

    Services that need to _write_ memories (SessionStore, OrchestratorService)
    depend on this, not on the concrete ButlerMemoryStore, so they remain
    testable without Redis/Postgres/TurboQuant.
    """

    @abstractmethod
    async def write(self, request: Any) -> Any:
        """Dispatch a MemoryWriteRequest through the policy router."""

    @abstractmethod
    async def archive(self, account_id: str, entry_id: Any) -> None:
        """Mark a memory record as deprecated across all tiers."""


class IColdStore(DomainService):
    """Abstraction over TurboQuantColdStore.

    Any service that needs cold-tier recall (session context assembly)
    should depend on this contract, keeping pyturboquant behind the boundary.
    """

    @abstractmethod
    async def recall(self, account_id: str, query: str, top_k: int = 5) -> List[Any]:
        """Return ranked cold-tier memory results for a query."""

    @abstractmethod
    def index(self, entry_id: str, embedding: List[float], payload: dict) -> None:
        """Index a new embedding into the cold store."""


class IRetrievalEngine(DomainService):
    """Abstraction over RetrievalFusionEngine.

    EvolutionEngine uses retrieval for fact reconciliation; it should not
    import the concrete fusion engine — only the search contract.
    """

    @abstractmethod
    async def search(
        self,
        account_id: str,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Any]:
        """Return ScoredMemory results for a query."""


class IMemoryRecorder(DomainService):
    """Narrow slice of MemoryServiceContract used by EpisodicMemoryEngine.

    Eliminates the circular dependency + monkey-patch anti-pattern:
    EpisodicMemoryEngine previously received a full MemoryService reference
    that was set after construction. Now it receives only this narrow
    interface at construction time.
    """

    @abstractmethod
    async def store(self, account_id: str, memory_type: str, content: dict, **kwargs) -> MemoryEntry:
        """Store a new memory entry."""

    @abstractmethod
    async def get_session_history(
        self, account_id: str, session_id: str, limit: int = 50
    ) -> list[ConversationTurn]:
        """Get conversation history for a session."""
