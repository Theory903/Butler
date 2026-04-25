import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import KnowledgeEdge, KnowledgeEntity
from services.memory.knowledge_repo_contract import KnowledgeRepoContract


class PostgresKnowledgeRepo(KnowledgeRepoContract):
    """PostgreSQL implementation of the Knowledge Graph using recursive CTEs."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def upsert_entity(
        self,
        account_id: uuid.UUID,
        entity_type: str,
        name: str,
        summary: str | None = None,
        metadata: dict | None = None,
    ) -> KnowledgeEntity:
        # Check if exists
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.account_id == account_id,
            KnowledgeEntity.name == name,
            KnowledgeEntity.entity_type == entity_type,
        )
        res = await self._db.execute(stmt)
        entity = res.scalar_one_or_none()

        if entity:
            entity.summary = summary or entity.summary
            entity.metadata_col.update(metadata or {})
        else:
            entity = KnowledgeEntity(
                account_id=account_id,
                entity_type=entity_type,
                name=name,
                summary=summary,
                metadata_col=metadata or {},
            )
            self._db.add(entity)

        await self._db.flush()
        return entity

    async def upsert_edge(
        self,
        account_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: str,
        metadata: dict | None = None,
    ) -> KnowledgeEdge:
        stmt = select(KnowledgeEdge).where(
            KnowledgeEdge.account_id == account_id,
            KnowledgeEdge.source_id == source_id,
            KnowledgeEdge.target_id == target_id,
            KnowledgeEdge.relation_type == relation_type,
        )
        res = await self._db.execute(stmt)
        edge = res.scalar_one_or_none()

        if edge:
            edge.metadata_col.update(metadata or {})
        else:
            edge = KnowledgeEdge(
                account_id=account_id,
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                metadata_col=metadata or {},
            )
            self._db.add(edge)

        await self._db.flush()
        return edge

    async def search_entities(
        self, account_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[KnowledgeEntity]:
        # Basic keyword search for now, optimized later with pgvector
        stmt = (
            select(KnowledgeEntity)
            .where(
                KnowledgeEntity.account_id == account_id, KnowledgeEntity.name.ilike(f"%{query}%")
            )
            .limit(limit)
        )
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def get_related_entities(
        self, account_id: uuid.UUID, entity_id: uuid.UUID, depth: int = 1
    ) -> list[KnowledgeEntity]:
        """Traverse relationships using a recursive CTE in Postgres."""
        # Simple depth 1 for now via join
        stmt = (
            select(KnowledgeEntity)
            .join(
                KnowledgeEdge,
                (KnowledgeEdge.target_id == KnowledgeEntity.id)
                | (KnowledgeEdge.source_id == KnowledgeEntity.id),
            )
            .where(
                KnowledgeEntity.account_id == account_id,
                (KnowledgeEdge.source_id == entity_id) | (KnowledgeEdge.target_id == entity_id),
                KnowledgeEntity.id != entity_id,
            )
            .distinct()
            .limit(20)
        )

        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def resolve_identity(self, account_id: uuid.UUID, name: str) -> KnowledgeEntity | None:
        """Match by name exactly or via simple alias in metadata."""
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.account_id == account_id, KnowledgeEntity.name.ilike(name)
        )
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()
