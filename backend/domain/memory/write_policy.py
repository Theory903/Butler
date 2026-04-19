"""Butler Memory Write Policy Engine.

Decides which storage tier(s) receive every memory write. This is Butler's
canonical routing authority — no Hermes memory plugin may override it.

Tiers:
  HOT    — Redis (<5ms)           last 20 turns, active workflow context
  WARM   — Qdrant full precision  recent/important episodes, all entities
  COLD   — pyturboquant           long-tail episodic, web chunks, old traces
  GRAPH  — Neo4j                  relationships, entity network
  STRUCT — PostgreSQL             structured facts, preferences, audit

Governed by: docs/00-governance/transplant-constitution.md §6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StorageTier(str, Enum):
    HOT    = "hot"     # Redis
    WARM   = "warm"    # Qdrant warm (full precision)
    COLD   = "cold"    # pyturboquant compressed
    GRAPH  = "graph"   # Neo4j
    STRUCT = "struct"  # PostgreSQL


@dataclass
class MemoryWriteRequest:
    """A memory item that needs to be routed to storage tier(s)."""
    memory_type: str          # session_message | preference | dislike | relationship |
                              # episode | entity | tool_trace | web_crawl_chunk |
                              # email_chunk | document_chunk | meeting_chunk
    content: Any
    importance: float = 0.5   # 0.0 – 1.0
    age_days: float = 0.0     # How old is this item already (for archive routing)
    account_id: str = ""
    session_id: str | None = None
    provenance: str = "conversation"  # conversation | tool | crawl | import | system
    has_pii: bool = False
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WriteRoute:
    """Result of the policy engine — which tiers to write to and why."""
    tiers: list[StorageTier]
    reason: str
    requires_provenance: bool = True    # Always true in Butler
    requires_audit_log: bool = False    # True for L2+ actions

    @property
    def primary_tier(self) -> StorageTier:
        return self.tiers[0] if self.tiers else StorageTier.STRUCT


class MemoryWritePolicy:
    """Routes every memory write to the correct storage tier(s).

    Rules:
      - Every write gets provenance metadata added by Butler BEFORE storage
      - Hermes memory backends are auxiliary providers that may receive
        copies, but PostgreSQL is always the canonical record for facts,
        preferences, and relationships
      - Hermes SessionDB receives session_message types only
      - pyturboquant cold tier receives high-volume/old/archival content only

    Usage:
        policy = MemoryWritePolicy()
        route = policy.route(request)
        for tier in route.tiers:
            await storage_manager.write(tier, request, provenance=...)
    """

    def route(self, request: MemoryWriteRequest) -> WriteRoute:
        match request.memory_type:

            # ── Conversation messages ─────────────────────────────────────────
            case "session_message":
                return WriteRoute(
                    tiers=[StorageTier.HOT],
                    reason="session_messages are ephemeral hot-tier only; "
                           "HermesSessionDB receives a copy for FTS replay",
                )

            # ── Preferences / Dislikes ────────────────────────────────────────
            case "preference" | "dislike":
                return WriteRoute(
                    tiers=[StorageTier.STRUCT, StorageTier.WARM, StorageTier.GRAPH],
                    reason="preferences are canonical in PostgreSQL + searchable "
                           "in Qdrant warm + traversable in Neo4j entity graph",
                )

            # ── Relationships ─────────────────────────────────────────────────
            case "relationship":
                return WriteRoute(
                    tiers=[StorageTier.GRAPH, StorageTier.STRUCT],
                    reason="relationships are primary in Neo4j; "
                           "structured fact record in PostgreSQL for audit",
                )

            # ── Entity facts ──────────────────────────────────────────────────
            case "entity":
                return WriteRoute(
                    tiers=[StorageTier.STRUCT, StorageTier.WARM, StorageTier.GRAPH],
                    reason="entity facts in PostgreSQL + Qdrant for embedding search "
                           "+ Neo4j for graph traversal",
                )

            # ── Episodic memories — tiered by age and importance ──────────────
            case "episode":
                if request.age_days > 30:
                    return WriteRoute(
                        tiers=[StorageTier.COLD, StorageTier.STRUCT],
                        reason="old episode (>30d) → pyturboquant cold + PostgreSQL record",
                    )
                if request.importance >= 0.7:
                    return WriteRoute(
                        tiers=[StorageTier.WARM, StorageTier.STRUCT],
                        reason="high-importance episode → Qdrant warm (full precision) + PostgreSQL",
                    )
                return WriteRoute(
                    tiers=[StorageTier.WARM, StorageTier.STRUCT],
                    reason="standard episode → Qdrant warm + PostgreSQL",
                )

            # ── Tool execution traces ─────────────────────────────────────────
            case "tool_trace":
                if request.age_days > 7:
                    return WriteRoute(
                        tiers=[StorageTier.COLD],
                        reason="old tool trace (>7d) → pyturboquant cold only",
                        requires_audit_log=False,
                    )
                return WriteRoute(
                    tiers=[StorageTier.STRUCT],
                    reason="recent tool trace → PostgreSQL tool_executions table",
                    requires_audit_log=True,
                )

            # ── Web/crawl/research chunks ─────────────────────────────────────
            case "web_crawl_chunk":
                return WriteRoute(
                    tiers=[StorageTier.COLD],
                    reason="web crawl chunks → pyturboquant cold tier (bulk, low retention)",
                )

            # ── Document, email, meeting chunks ──────────────────────────────
            case "email_chunk" | "document_chunk" | "meeting_chunk":
                if request.age_days > 60:
                    return WriteRoute(
                        tiers=[StorageTier.COLD],
                        reason="old document chunk → pyturboquant cold tier archive",
                    )
                return WriteRoute(
                    tiers=[StorageTier.WARM, StorageTier.STRUCT],
                    reason="recent document chunk → Qdrant warm + PostgreSQL",
                )

            # ── Default: safe fallback to warm Qdrant ────────────────────────
            case _:
                return WriteRoute(
                    tiers=[StorageTier.WARM],
                    reason=f"unknown memory type '{request.memory_type}' → Qdrant warm default",
                )

    def should_write_hermes_session_db(self, request: MemoryWriteRequest) -> bool:
        """Hermes SessionDB receives session_message copies for FTS replay only."""
        return request.memory_type == "session_message"

    def should_write_hermes_plugin(
        self, request: MemoryWriteRequest, plugin: str
    ) -> bool:
        """Whether an auxiliary Hermes memory plugin should receive a copy.

        Hermes plugins (mem0, hindsight, supermemory, etc.) may receive copies
        of episodic + entity data for their own recall patterns. They are never
        the Butler source of truth.

        Butler config controls which plugins are active per deployment.
        """
        if request.memory_type in ("session_message",):
            return False  # These stay in Butler+Hermes SessionDB only
        if request.memory_type in ("tool_trace", "web_crawl_chunk"):
            return False  # Too high volume; not useful for plugins
        # Episodic, preference, entity → optional plugin copy
        return request.memory_type in ("episode", "preference", "entity", "relationship")

    def enforce_pii_rules(self, request: MemoryWriteRequest, tier: StorageTier) -> bool:
        """Returns False if PII data must NOT be written to this tier.

        Cold tier (pyturboquant) does not support fine-grained deletion —
        PII-tagged items must not be routed there.
        """
        if request.has_pii and tier == StorageTier.COLD:
            return False  # pyturboquant cold cannot satisfy right-to-erasure
        return True
