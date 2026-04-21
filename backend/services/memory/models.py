"""4-Tier Memory Model Definitions (Digital Twin).

This module defines the architectural boundaries for the four tiers of Butler's
memory system, spanning ephemeral context to permanent structural graph knowledge.

Tiers:
1. Short-Term (Working Memory / Sliding Window)
2. Episodic (Vector Store / Qdrant)
3. Structural (Knowledge Graph / Neo4j)
4. Cold Storage (FAISS / Object Store / Compressed)
"""

import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, UTC


class BaseMemoryArtifact(BaseModel):
    """Common foundation for all memory representations."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    account_id: uuid.UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(from_attributes=True)


class WorkingMemoryTier(BaseMemoryArtifact):
    """Tier 1: Short-term contextual window.
    
    Holds recent chat histories, current active tool states, and uncommitted
    working scratchpads. Flushed routinely to Episodic Memory.
    """
    session_id: str
    active_tokens: int
    context_window: List[Dict[str, Any]] = Field(default_factory=list)
    epoch_summaries: List[str] = Field(default_factory=list)


class EpisodicMemoryTier(BaseMemoryArtifact):
    """Tier 2: Vector-based semantic search (Qdrant).
    
    Stores conversational chunks, tool outputs, and document embeddings.
    Indexed purely by time and semantic similarity.
    """
    vector_id: str
    content: str
    embedding_source: str
    timestamp: datetime
    ttl_expires_at: Optional[datetime] = None


class StructuralMemoryTier(BaseMemoryArtifact):
    """Tier 3: Relational Knowledge Graph (Neo4j).
    
    Stores explicitly extracted entities, relationships, attributes, and
    notebook entries. Highly curated and explicitly verified.
    """
    entity_id: str
    entity_class: str
    name: str
    attributes: Dict[str, Any]
    relations: List[Dict[str, Any]]


class ColdStorageTier(BaseMemoryArtifact):
    """Tier 4: Compressed Archives (FAISS/S3).
    
    Stores fully dormant memory graphs, stale Qdrant snapshots, and raw
    ingested zip files containing ancient chat history.
    """
    archive_key: str
    compressed_size_bytes: int
    hash_signature: str
    retrieval_latency_ms: int = 5000
