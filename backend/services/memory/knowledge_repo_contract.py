from abc import abstractmethod
from uuid import UUID

from domain.base import DomainService
from domain.memory.models import KnowledgeEdge, KnowledgeEntity


class KnowledgeRepoContract(DomainService):
    """Contract for Knowledge Graph storage (Neo4j or Postgres)."""

    @abstractmethod
    async def upsert_entity(
        self,
        account_id: UUID,
        entity_type: str,
        name: str,
        summary: str | None = None,
        metadata: dict | None = None,
        tenant_id: UUID | None = None,
    ) -> KnowledgeEntity:
        """Upsert a canonical entity."""

    @abstractmethod
    async def upsert_edge(
        self,
        account_id: UUID,
        source_id: UUID,
        target_id: UUID,
        relation_type: str,
        metadata: dict | None = None,
        tenant_id: UUID | None = None,
    ) -> KnowledgeEdge:
        """Upsert a relationship between entities."""

    @abstractmethod
    async def search_entities(
        self, account_id: UUID, query: str, limit: int = 10, tenant_id: UUID | None = None
    ) -> list[KnowledgeEntity]:
        """Search entities by name or summary (graph-aware)."""

    @abstractmethod
    async def get_related_entities(
        self, account_id: UUID, entity_id: UUID, depth: int = 1, tenant_id: UUID | None = None
    ) -> list[KnowledgeEntity]:
        """Traverse the graph to find related entities."""

    @abstractmethod
    async def resolve_identity(self, account_id: UUID, name: str, tenant_id: UUID | None = None) -> KnowledgeEntity | None:
        """Resolve a name (or alias) to a canonical KnowledgeEntity."""
