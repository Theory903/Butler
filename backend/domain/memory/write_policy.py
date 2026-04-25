from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StorageTier(StrEnum):
    HOT = "hot"  # Redis
    WARM = "warm"  # Qdrant / full-precision vector tier
    COLD = "cold"  # FAISS / TurboQuant archival tier
    GRAPH = "graph"  # Neo4j
    STRUCT = "struct"  # PostgreSQL canonical record


@dataclass(slots=True)
class MemoryWriteRequest:
    """Canonical write request for Butler memory routing.

    Canonical memory types expected by Butler:
      - session_message
      - preference
      - dislike
      - relationship
      - entity
      - episode
      - tool_trace
      - web_crawl_chunk
      - email_chunk
      - document_chunk
      - meeting_chunk
      - research_chunk
      - summary_anchor
      - workflow_state
      - audit_event
    """

    memory_type: str
    content: Any
    importance: float = 0.5
    age_days: float = 0.0
    account_id: str = ""
    session_id: str | None = None
    provenance: str = "conversation"  # conversation | tool | crawl | import | system
    has_pii: bool = False
    is_scrubbed: bool = False
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WriteRoute:
    """Policy output describing where a write should go and why."""

    tiers: list[StorageTier]
    reason: str
    requires_provenance: bool = True
    requires_audit_log: bool = False

    @property
    def primary_tier(self) -> StorageTier:
        if self.tiers:
            return self.tiers[0]
        return StorageTier.STRUCT


class MemoryWritePolicy:
    """Canonical Butler memory routing policy.

    Design rules:
      - PostgreSQL STRUCT is the canonical source of truth for durable facts,
        preferences, relationships, summaries, and audit-relevant items.
      - HOT is for short-lived rolling conversational/session context.
      - WARM is for active semantic retrieval.
      - COLD is for archival / long-tail / high-volume material only.
      - GRAPH is for entities and relationships that benefit from traversal.
      - Hermes-side memory copies are auxiliary only and never canonical.
    """

    def __init__(self, consent_manager: Any | None = None) -> None:
        self._consent = consent_manager

    _GRAPH_TYPES: frozenset[str] = frozenset(
        {
            "entity",
            "relationship",
            "preference",
            "dislike",
        }
    )

    _STRUCT_REQUIRED_TYPES: frozenset[str] = frozenset(
        {
            "preference",
            "dislike",
            "relationship",
            "entity",
            "episode",
            "document_chunk",
            "email_chunk",
            "meeting_chunk",
            "research_chunk",
            "summary_anchor",
            "workflow_state",
            "audit_event",
            "tool_trace",
        }
    )

    _CHUNK_TYPES: frozenset[str] = frozenset(
        {
            "web_crawl_chunk",
            "email_chunk",
            "document_chunk",
            "meeting_chunk",
            "research_chunk",
        }
    )

    def route(self, request: MemoryWriteRequest) -> WriteRoute:
        memory_type = self._normalize_memory_type(request.memory_type)

        if memory_type == "session_message":
            return self._route_session_message(request)

        if memory_type in {"preference", "dislike"}:
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.WARM,
                        StorageTier.GRAPH,
                    ]
                ),
                reason=(
                    "preferences/dislikes are durable user-profile facts: "
                    "STRUCT canonical, WARM searchable, GRAPH traversable"
                ),
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        if memory_type == "relationship":
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.GRAPH,
                        StorageTier.STRUCT,
                        StorageTier.WARM
                        if self._should_semantically_index_relationship(request)
                        else None,
                    ]
                ),
                reason=(
                    "relationships are graph-first and must retain a canonical "
                    "structured audit record"
                ),
                requires_provenance=True,
                requires_audit_log=True,
            )

        if memory_type == "entity":
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.WARM,
                        StorageTier.GRAPH,
                    ]
                ),
                reason=(
                    "entities are durable structured records with semantic search "
                    "and graph traversal requirements"
                ),
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        if memory_type == "episode":
            return self._route_episode(request)

        if memory_type == "tool_trace":
            return self._route_tool_trace(request)

        if memory_type in self._CHUNK_TYPES:
            return self._route_chunk(request, memory_type)

        if memory_type == "summary_anchor":
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.HOT if request.session_id else None,
                        StorageTier.WARM,
                    ]
                ),
                reason=(
                    "session summary anchors are durable structured context artifacts "
                    "and should also remain retrievable semantically"
                ),
                requires_provenance=True,
                requires_audit_log=False,
            )

        if memory_type == "workflow_state":
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.HOT if request.session_id else None,
                    ]
                ),
                reason=(
                    "workflow state is canonical operational state and may also need "
                    "short-lived hot-session availability"
                ),
                requires_provenance=True,
                requires_audit_log=True,
            )

        if memory_type == "audit_event":
            return WriteRoute(
                tiers=[StorageTier.STRUCT],
                reason="audit events must be canonical and immutable in structured storage",
                requires_provenance=True,
                requires_audit_log=True,
            )

        return WriteRoute(
            tiers=self._dedupe_tiers(
                [
                    StorageTier.STRUCT,
                    StorageTier.WARM,
                    StorageTier.GRAPH if self._looks_graph_worthy(request) else None,
                ]
            ),
            reason=(
                f"unknown memory type '{memory_type}' routed safely to canonical "
                "STRUCT plus WARM semantic retrieval"
            ),
            requires_provenance=True,
            requires_audit_log=self._is_audit_sensitive(request),
        )

    def should_write_hermes_session_db(self, request: MemoryWriteRequest) -> bool:
        """Hermes SessionDB is only a sidecar for session-message replay/search."""
        memory_type = self._normalize_memory_type(request.memory_type)
        return memory_type == "session_message"

    def should_write_hermes_plugin(self, request: MemoryWriteRequest, plugin: str) -> bool:
        """Whether an auxiliary Hermes plugin may receive a non-canonical copy."""
        del plugin

        memory_type = self._normalize_memory_type(request.memory_type)

        if memory_type == "session_message":
            return False

        if memory_type in {"tool_trace", "audit_event", "workflow_state"}:
            return False

        if memory_type in {"web_crawl_chunk"}:
            return False

        return memory_type in {
            "episode",
            "preference",
            "dislike",
            "entity",
            "relationship",
            "summary_anchor",
            "document_chunk",
            "email_chunk",
            "meeting_chunk",
            "research_chunk",
        }

    def enforce_pii_rules(self, request: MemoryWriteRequest, tier: StorageTier) -> bool:
        """Enforce storage-tier privacy constraints.

        Current hard rule:
          - PII must not be routed to COLD because cold archival backends may not
            support precise right-to-erasure semantics.
          - If ConsentManager is present and policy says scrub_pii, then PII is only
            allowed if it has already been scrubbed.

        Soft detection fallback:
          - if request.has_pii is false but metadata says sensitivity/high/pii,
            we still treat it as PII-sensitive for routing.
        """
        pii_sensitive = self._has_effective_pii(request)

        if pii_sensitive and tier == StorageTier.COLD:
            return False

        if self._consent is not None and request.account_id:
            import uuid

            try:
                acc_uuid = uuid.UUID(request.account_id)
                policy = self._consent.get_policy(acc_uuid)

                # If policy requires scrubbing, and we still have unscrubbed PII,
                # we block writes to sensitive tiers (WARM, STRUCT, GRAPH)
                # until it is scrubbed.
                if policy.get("scrub_pii", True) and pii_sensitive and not request.is_scrubbed:
                    # In practice, the MemoryStore should have scrubbed it already.
                    # This is a safety gate.
                    return False
            except (ValueError, TypeError, AttributeError):
                pass

        return True

    def _route_session_message(self, request: MemoryWriteRequest) -> WriteRoute:
        """Session messages are hot by default, optionally durable when required."""
        durable = self._session_message_requires_struct(request)

        if durable:
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.HOT,
                        StorageTier.STRUCT,
                    ]
                ),
                reason=(
                    "session message requires both hot conversational availability "
                    "and structured durability/audit"
                ),
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        return WriteRoute(
            tiers=[StorageTier.HOT],
            reason=(
                "session message is short-lived conversational context; "
                "Hermes SessionDB may receive a replay/search copy"
            ),
            requires_provenance=True,
            requires_audit_log=False,
        )

    def _route_episode(self, request: MemoryWriteRequest) -> WriteRoute:
        if request.age_days > 30:
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.COLD,
                    ]
                ),
                reason=("older episode routed to canonical STRUCT plus archival COLD tier"),
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        if request.importance >= 0.85:
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.WARM,
                        StorageTier.GRAPH if self._looks_graph_worthy(request) else None,
                    ]
                ),
                reason=("high-importance episode kept canonical in STRUCT and active in WARM"),
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        return WriteRoute(
            tiers=self._dedupe_tiers(
                [
                    StorageTier.STRUCT,
                    StorageTier.WARM,
                ]
            ),
            reason="recent episode kept in canonical STRUCT and active WARM retrieval",
            requires_provenance=True,
            requires_audit_log=self._is_audit_sensitive(request),
        )

    def _route_tool_trace(self, request: MemoryWriteRequest) -> WriteRoute:
        if request.age_days > 7 and not self._is_audit_sensitive(request):
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.COLD,
                    ]
                ),
                reason=(
                    "older non-critical tool trace retained canonically in STRUCT and "
                    "archived to COLD for long-tail diagnostics"
                ),
                requires_provenance=True,
                requires_audit_log=False,
            )

        return WriteRoute(
            tiers=[StorageTier.STRUCT],
            reason="recent or audit-relevant tool trace must remain structured and durable",
            requires_provenance=True,
            requires_audit_log=True,
        )

    def _route_chunk(self, request: MemoryWriteRequest, memory_type: str) -> WriteRoute:
        if memory_type == "web_crawl_chunk":
            if request.age_days > 14 or request.importance < 0.35:
                return WriteRoute(
                    tiers=[StorageTier.COLD],
                    reason="bulk/older crawl chunk routed to archival cold tier",
                    requires_provenance=True,
                    requires_audit_log=False,
                )

            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.WARM,
                        StorageTier.STRUCT
                        if self._should_keep_structured_chunk_record(request)
                        else None,
                    ]
                ),
                reason="recent/high-value crawl chunk kept warm for active retrieval",
                requires_provenance=True,
                requires_audit_log=False,
            )

        if request.age_days > 60:
            return WriteRoute(
                tiers=self._dedupe_tiers(
                    [
                        StorageTier.STRUCT,
                        StorageTier.COLD,
                    ]
                ),
                reason="older document-like chunk retained canonically and archived cold",
                requires_provenance=True,
                requires_audit_log=self._is_audit_sensitive(request),
            )

        return WriteRoute(
            tiers=self._dedupe_tiers(
                [
                    StorageTier.STRUCT,
                    StorageTier.WARM,
                ]
            ),
            reason="recent document-like chunk kept in canonical STRUCT plus WARM retrieval",
            requires_provenance=True,
            requires_audit_log=self._is_audit_sensitive(request),
        )

    def _normalize_memory_type(self, memory_type: str) -> str:
        normalized = (memory_type or "").strip().lower()
        return normalized or "unknown"

    def _dedupe_tiers(self, tiers: list[StorageTier | None]) -> list[StorageTier]:
        result: list[StorageTier] = []
        seen: set[StorageTier] = set()

        for tier in tiers:
            if tier is None:
                continue
            if tier in seen:
                continue
            seen.add(tier)
            result.append(tier)

        return result

    def _session_message_requires_struct(self, request: MemoryWriteRequest) -> bool:
        metadata = request.metadata or {}

        return any(
            [
                bool(metadata.get("durable")),
                bool(metadata.get("audit")),
                bool(metadata.get("requires_struct")),
                bool(metadata.get("tool_call")),
                bool(metadata.get("contains_decision")),
                bool(metadata.get("contains_artifact_reference")),
                request.importance >= 0.8,
            ]
        )

    def _should_semantically_index_relationship(self, request: MemoryWriteRequest) -> bool:
        return request.importance >= 0.6

    def _should_keep_structured_chunk_record(self, request: MemoryWriteRequest) -> bool:
        return any(
            [
                request.importance >= 0.6,
                self._is_audit_sensitive(request),
                bool((request.metadata or {}).get("durable")),
            ]
        )

    def _looks_graph_worthy(self, request: MemoryWriteRequest) -> bool:
        metadata = request.metadata or {}

        if self._normalize_memory_type(request.memory_type) in self._GRAPH_TYPES:
            return True

        return any(
            [
                bool(metadata.get("entity_name")),
                bool(metadata.get("entity_id")),
                bool(metadata.get("relationship")),
                bool(metadata.get("source_name") and metadata.get("target_name")),
            ]
        )

    def _is_audit_sensitive(self, request: MemoryWriteRequest) -> bool:
        metadata = request.metadata or {}

        return any(
            [
                bool(metadata.get("audit")),
                bool(metadata.get("approval_required")),
                bool(metadata.get("security_relevant")),
                bool(metadata.get("external_side_effect")),
                request.provenance in {"tool", "system"},
            ]
        )

    def _has_effective_pii(self, request: MemoryWriteRequest) -> bool:
        if request.has_pii:
            return True

        metadata = request.metadata or {}
        sensitivity = str(metadata.get("sensitivity", "")).strip().lower()

        if sensitivity in {"pii", "high", "sensitive"}:
            return True

        pii_flag = metadata.get("contains_pii")
        return bool(isinstance(pii_flag, bool) and pii_flag)
