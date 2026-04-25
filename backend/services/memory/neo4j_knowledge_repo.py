import uuid

from domain.memory.models import KnowledgeEdge, KnowledgeEntity
from infrastructure.memory.neo4j_client import neo4j_client
from services.memory.knowledge_repo_contract import KnowledgeRepoContract


class Neo4jKnowledgeRepo(KnowledgeRepoContract):
    """Neo4j implementation of the Knowledge Graph (Oracle-Grade)."""

    def __init__(self):
        self._client = neo4j_client

    async def upsert_entity(
        self,
        account_id: uuid.UUID,
        entity_type: str,
        name: str,
        summary: str | None = None,
        metadata: dict | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> KnowledgeEntity:
        query = """
        MERGE (e:KnowledgeEntity {account_id: $account_id, tenant_id: $tenant_id, name: $name, entity_type: $entity_type})
        ON CREATE SET e.id = $id,
                      e.created_at = datetime(),
                      e.status = 'active',
                      e.valid_from = datetime()
        SET e.summary = $summary,
            e.metadata = $metadata,
            e.updated_at = datetime()
        RETURN e
        """
        params = {
            "id": str(uuid.uuid4()),
            "account_id": str(account_id),
            "tenant_id": str(tenant_id) if tenant_id else str(account_id),
            "name": name,
            "entity_type": entity_type,
            "summary": summary,
            "metadata": metadata or {},
        }

        await self._client.execute_query(query, params)

        return KnowledgeEntity(
            id=uuid.UUID(params["id"]),
            account_id=account_id,
            entity_type=entity_type,
            name=name,
            summary=summary,
            metadata_col=metadata or {},
        )

    async def archive_entity(
        self, account_id: uuid.UUID, entity_id: uuid.UUID, superseded_by: uuid.UUID | None = None, tenant_id: uuid.UUID | None = None
    ):
        """Standard archival logic for the Neo4j tier."""
        query = """
        MATCH (e:KnowledgeEntity {account_id: $account_id, tenant_id: $tenant_id, id: $entity_id})
        SET e.status = 'deprecated',
            e.valid_until = datetime(),
            e.superseded_by = $superseded_by
        """
        params = {
            "account_id": str(account_id),
            "tenant_id": str(tenant_id) if tenant_id else str(account_id),
            "entity_id": str(entity_id),
            "superseded_by": str(superseded_by) if superseded_by else None,
        }
        await self._client.execute_query(query, params)

    async def store_chunk(
        self,
        account_id: uuid.UUID,
        chunk_id: uuid.UUID,
        text: str,
        source_id: uuid.UUID,
        source_type: str,
        entity_ids: list[uuid.UUID],
        tenant_id: uuid.UUID | None = None,
    ):
        """Butler-native: Source Attribution. Link Chunks to Entities."""
        query = """
        MERGE (c:KnowledgeChunk {id: $chunk_id, account_id: $account_id, tenant_id: $tenant_id})
        SET c.text = $text,
            c.source_id = $source_id,
            c.source_type = $source_type,
            c.created_at = datetime()
        WITH c
        UNWIND $entity_ids AS ent_id
        MATCH (e:KnowledgeEntity {id: ent_id, account_id: $account_id, tenant_id: $tenant_id})
        MERGE (c)-[:HAS_ENTITY]->(e)
        """
        params = {
            "account_id": str(account_id),
            "tenant_id": str(tenant_id) if tenant_id else str(account_id),
            "chunk_id": str(chunk_id),
            "text": text,
            "source_id": str(source_id),
            "source_type": source_type,
            "entity_ids": [str(eid) for eid in entity_ids],
        }
        await self._client.execute_query(query, params)

    async def get_graph_context(
        self, account_id: uuid.UUID, entity_names: list[str], depth: int = 1, tenant_id: uuid.UUID | None = None
    ) -> list[dict]:
        """Graph-Vector Expansion: Find entities and their neighborhood context."""
        cypher = f"""
        MATCH (e:KnowledgeEntity {{account_id: $account_id, tenant_id: $tenant_id}})
        WHERE e.name IN $entity_names AND e.status = 'active'
        MATCH (e)-[r*1..{depth}]-(related:KnowledgeEntity {{tenant_id: $tenant_id, status: 'active'}})
        RETURN e.name AS source, type(r[0]) AS relation, related.name AS target, related.summary AS summary
        LIMIT 50
        """
        params = {"account_id": str(account_id), "tenant_id": str(tenant_id) if tenant_id else str(account_id), "entity_names": entity_names}
        return await self._client.execute_query(cypher, params)

    async def upsert_edge(
        self,
        account_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: str,
        metadata: dict | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> KnowledgeEdge:
        # We sanitize the relation type for Cypher
        rel_type = relation_type.upper().replace(" ", "_")
        query = f"""
        MATCH (s:KnowledgeEntity {{account_id: $account_id, tenant_id: $tenant_id, id: $source_id}})
        MATCH (t:KnowledgeEntity {{account_id: $account_id, tenant_id: $tenant_id, id: $target_id}})
        MERGE (s)-[r:{rel_type}]->(t)
        SET r.metadata = $metadata,
            r.updated_at = datetime()
        RETURN r
        """
        params = {
            "account_id": str(account_id),
            "tenant_id": str(tenant_id) if tenant_id else str(account_id),
            "source_id": str(source_id),
            "target_id": str(target_id),
            "metadata": metadata or {},
        }

        await self._client.execute_query(query, params)

        return KnowledgeEdge(
            account_id=account_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata_col=metadata or {},
        )

    async def search_entities(
        self, account_id: uuid.UUID, query: str, limit: int = 10, tenant_id: uuid.UUID | None = None
    ) -> list[KnowledgeEntity]:
        # Using full-text search index if available in Neo4j
        cypher = """
        MATCH (e:KnowledgeEntity {account_id: $account_id, tenant_id: $tenant_id, status: 'active'})
        WHERE e.name CONTAINS $query OR e.summary CONTAINS $query
        RETURN e LIMIT $limit
        """
        params = {"account_id": str(account_id), "tenant_id": str(tenant_id) if tenant_id else str(account_id), "query": query, "limit": limit}
        results = await self._client.execute_query(cypher, params)

        return [self._map_node_to_entity(r["e"]) for r in results]

    async def get_related_entities(
        self, account_id: uuid.UUID, entity_id: uuid.UUID, depth: int = 1, tenant_id: uuid.UUID | None = None
    ) -> list[KnowledgeEntity]:
        cypher = f"""
        MATCH (e:KnowledgeEntity {{account_id: $account_id, tenant_id: $tenant_id, id: $entity_id, status: 'active'}})-[*1..{depth}]-(related:KnowledgeEntity {{tenant_id: $tenant_id, status: 'active'}})
        RETURN DISTINCT related LIMIT 20
        """
        params = {"account_id": str(account_id), "tenant_id": str(tenant_id) if tenant_id else str(account_id), "entity_id": str(entity_id)}
        results = await self._client.execute_query(cypher, params)

        return [self._map_node_to_entity(r["related"]) for r in results]

    async def resolve_identity(self, account_id: uuid.UUID, name: str, tenant_id: uuid.UUID | None = None) -> KnowledgeEntity | None:
        cypher = """
        MATCH (e:KnowledgeEntity {account_id: $account_id, tenant_id: $tenant_id, status: 'active'})
        WHERE e.name =~ $name_regex
        RETURN e LIMIT 1
        """
        params = {"account_id": str(account_id), "tenant_id": str(tenant_id) if tenant_id else str(account_id), "name_regex": f"(?i){name}"}
        results = await self._client.execute_query(cypher, params)

        if results:
            return self._map_node_to_entity(results[0]["e"])
        return None

    def _map_node_to_entity(self, node_data: dict) -> KnowledgeEntity:
        return KnowledgeEntity(
            id=uuid.UUID(node_data["id"]),
            account_id=uuid.UUID(node_data["account_id"]),
            entity_type=node_data["entity_type"],
            name=node_data["name"],
            summary=node_data.get("summary"),
            metadata_col=node_data.get("metadata", {}),
            status=node_data.get("status", "active"),
        )
