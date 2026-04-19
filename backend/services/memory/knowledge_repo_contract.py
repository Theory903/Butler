from abc import abstractmethod
from typing import List, Optional, Dict
from uuid import UUID
from domain.base import DomainService
from domain.memory.models import KnowledgeEntity, KnowledgeEdge

class KnowledgeRepoContract(DomainService):
    """Contract for Knowledge Graph storage (Neo4j or Postgres)."""
    
    @abstractmethod
    async def upsert_entity(self, account_id: UUID, entity_type: str, name: str, 
                           summary: Optional[str] = None, metadata: Optional[Dict] = None) -> KnowledgeEntity:
        """Upsert a canonical entity."""
        pass

    @abstractmethod
    async def upsert_edge(self, account_id: UUID, source_id: UUID, target_id: UUID, 
                         relation_type: str, metadata: Optional[Dict] = None) -> KnowledgeEdge:
        """Upsert a relationship between entities."""
        pass

    @abstractmethod
    async def search_entities(self, account_id: UUID, query: str, limit: int = 10) -> List[KnowledgeEntity]:
        """Search entities by name or summary (graph-aware)."""
        pass

    @abstractmethod
    async def get_related_entities(self, account_id: UUID, entity_id: UUID, depth: int = 1) -> List[KnowledgeEntity]:
        """Traverse the graph to find related entities."""
        pass

    @abstractmethod
    async def resolve_identity(self, account_id: UUID, name: str) -> Optional[KnowledgeEntity]:
        """Resolve a name (or alias) to a canonical KnowledgeEntity."""
        pass
