import uuid
import logging
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, UTC

from domain.memory.models import KnowledgeChunk, KnowledgeEntity
from domain.ml.contracts import EmbeddingContract, IReasoningRuntime
from services.memory.knowledge_repo_contract import KnowledgeRepoContract

logger = logging.getLogger(__name__)

BUTLER_EXTRACTION_PROMPT = """
You are Butler's high-fidelity Knowledge Extraction Engine. Your goal is to extract structured entities and relations from the provided text to populate a personal knowledge graph.

### Extraction Policy:
1. **Precision over Recall**: Only extract entities that are clearly defined and useful for long-term memory. Avoid "noise" from generic chat filler.
2. **Explicitness**: Distinguish between things the user explicitly stated ("I love celery") and things you are inferring ("The user likely prefers healthy food").
3. **Butler Domain**: Focus on the following classes:
   - **Person / Organization**: People and groups in the user's life.
   - **Project / Task / Goal**: What the user is working on or wants to achieve.
   - **Preference / Dislike / Constraint**: User's tastes, values, and hard rules.
   - **Routine / Skill / Technology**: Recurring patterns, capabilities, and tools/stacks used.
   - **Device / Location / Asset**: Physical environment only when relevant to context.
   - **Topic**: Broad conceptual categories.

### Schema Adherence:
Return a JSON object with:
- "entities": list of {{ "name", "type", "summary", "is_explicit": bool, "confidence": 0.0-1.0 }}
- "relations": list of {{ "source", "target", "type", "is_explicit": bool }}

Valid Relation Types: PREFERS, DISLIKES, WORKS_ON, USES, OWNS, LOCATED_IN, RELATED_TO, DEPENDS_ON, PART_OF, WANTS, AVOIDS, LEARNED, MENTIONED_WITH.

### Text to Process:
{text}

Respond ONLY with the JSON object.
"""

class KnowledgeExtractionEngine:
    """Butler's high-fidelity graph extraction and chunking engine."""

    def __init__(
        self,
        embedder: EmbeddingContract,
        neo4j_repo: KnowledgeRepoContract,    # accepts any KnowledgeRepo impl
        ml_runtime: IReasoningRuntime,         # accepts any reasoning runtime
        chunk_size: int = 600,
        chunk_overlap: int = 100,
    ):
        self._embedder = embedder
        self._neo4j_repo = neo4j_repo
        self._ml_runtime = ml_runtime
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def extract_and_store(
        self, 
        account_id: str, 
        text: str, 
        source_id: uuid.UUID, 
        source_type: str,
        use_semantic_chunking: bool = False
    ) -> List[uuid.UUID]:
        """
        Main pipeline: Ingest -> Chunk -> Embed -> Extract Graph -> Store.
        """
        acc_id = uuid.UUID(account_id)
        
        # 1. Chunking logic
        chunks = self._recursive_split(text) if not use_semantic_chunking else self._semantic_split(text)
        
        chunk_ids = []
        for i, chunk_text in enumerate(chunks):
            # 2. Embedding
            embedding = await self._embedder.embed(chunk_text)
            chunk_id = uuid.uuid4()
            
            # 3. Extract Graph Elements
            extracted_entities, extracted_relations = await self._extract_entities_from_chunk(account_id, chunk_text)
            
            # 4. Store in Neo4j (Source Attribution)
            # Link chunk to extracted entities for provenance
            entity_ids = []
            entity_map = {}  # Resolves names locally
            
            for ent_data in extracted_entities:
                # Upsert entity to graph first
                ent_name = ent_data.get("name")
                if not ent_name:
                    continue
                    
                ent = await self._neo4j_repo.upsert_entity(
                    account_id=acc_id,
                    entity_type=ent_data.get("type", "Topic"),
                    name=ent_name,
                    summary=ent_data.get("summary"),
                    metadata={
                        "is_explicit": ent_data.get("is_explicit", True),
                        "confidence": ent_data.get("confidence", 1.0),
                        "extracted_at": datetime.now(UTC).isoformat()
                    }
                )
                entity_ids.append(ent.id)
                entity_map[ent_name.lower()] = ent.id
            
            # Upsert relational edges
            for rel_data in extracted_relations:
                src_name = rel_data.get("source", "").lower()
                tgt_name = rel_data.get("target", "").lower()
                
                if src_name in entity_map and tgt_name in entity_map:
                    await self._neo4j_repo.upsert_edge(
                        account_id=acc_id,
                        source_id=entity_map[src_name],
                        target_id=entity_map[tgt_name],
                        relation_type=rel_data.get("type", "RELATED_TO"),
                        metadata={
                            "is_explicit": rel_data.get("is_explicit", True)
                        }
                    )
            
            await self._neo4j_repo.store_chunk(
                account_id=acc_id,
                chunk_id=chunk_id,
                text=chunk_text,
                source_id=source_id,
                source_type=source_type,
                entity_ids=entity_ids
            )
            
            chunk_ids.append(chunk_id)
            
        logger.info(f"Extracted {len(chunk_ids)} chunks and graph links for source {source_id}")
        return chunk_ids

    def _recursive_split(self, text: str) -> List[str]:
        """Standard overlapping window split."""
        if not text:
            return []
            
        words = text.split()
        chunks = []
        for i in range(0, len(words), self._chunk_size - self._chunk_overlap):
            chunk_words = words[i:i + self._chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + self._chunk_size >= len(words):
                break
        return chunks

    def _semantic_split(self, text: str) -> List[str]:
        """Placeholder for topic-aware splitting."""
        logger.debug("Semantic splitting requested - falling back to recursive for Phase 11 baseline.")
        return self._recursive_split(text)

    async def _extract_entities_from_chunk(self, account_id: str, text: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Call LLM to extract entities following the 'Butler Preferred Schema'."""
        from domain.ml.contracts import ReasoningRequest
        prompt = BUTLER_EXTRACTION_PROMPT.format(text=text)

        try:
            req = ReasoningRequest(
                prompt=prompt,
                temperature=0.1,
                max_tokens=1024,
                metadata={"profile": "local-reasoning-qwen3"},
            )
            resp = await self._ml_runtime.generate(req)
            content = resp.content if hasattr(resp, "content") else resp.get("generated_text", "{}")

            # Basic cleanup if model wraps in code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            return data.get("entities", []), data.get("relations", [])

        except Exception as e:
            logger.error(f"Failed to extract entities for {account_id}: {e}")
            return [], []
