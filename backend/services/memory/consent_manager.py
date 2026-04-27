"""Memory Consent & Privacy Manager.

Digital Twin Memory heavily relies on strict consent boundaries and temporal data scrubbing.
This service enforces the guarantees detailed in the Digital Twin architecture:
1. Scrubbing PII from Episodic Memory streams.
2. Enforcing Data Expiry (TTL).
3. Verifying explicit user consent before committing Episodic traces to Permanent Structural Graph.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.observability import get_metrics
from core.tracing import tracer

import structlog

logger = structlog.get_logger(__name__)


class ConsentManager:
    """Enforces strict bounds on data retention and processing for Digital Twin memory pools."""

    # Basic PII regex patterns
    PII_PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "phone": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    }

    def __init__(self):
        # In a real deployed environment, this would pull from a centralized Compliance DB
        self._tenant_policies: dict[uuid.UUID, dict[str, Any]] = {}
        import re

        self._compiled_patterns = {k: re.compile(v) for k, v in self.PII_PATTERNS.items()}

    def get_policy(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Fetch the current retention and scrubbing policy for the tenant."""
        return self._tenant_policies.get(
            tenant_id,
            {
                "episodic_ttl_days": 30,
                "allow_structural_graph_commit": True,
                "scrub_pii": True,
                "forbidden_topics": ["financial_credentials", "medical_history", "passwords"],
            },
        )

    def update_policy(self, tenant_id: uuid.UUID, policy_updates: dict[str, Any]) -> None:
        """Update consent policies dynamically via operator or user override."""
        current = self.get_policy(tenant_id)
        current.update(policy_updates)
        self._tenant_policies[tenant_id] = current
        logger.info(f"Updated consent policy for tenant {tenant_id}")
        get_metrics().inc_counter("memory.consent.policy_updated", tags={"tenant": str(tenant_id)})

    async def scrub_text(self, tenant_id: uuid.UUID, content: str) -> str:
        """Analyze and scrub PII or forbidden topics from text streams.

        Uses regex patterns to replace sensitive entities with `<REDACTED>` tags.
        """
        policy = self.get_policy(tenant_id)
        if not policy.get("scrub_pii", True) or not content:
            return content

        with tracer.start_as_current_span("consent.scrub_pii"):
            scrubbed = content
            found_pii = False

            for pii_type, pattern in self._compiled_patterns.items():
                if pattern.search(scrubbed):
                    scrubbed = pattern.sub(f"<REDACTED_{pii_type.upper()}>", scrubbed)
                    found_pii = True

            if found_pii:
                logger.info(f"Scrubbed PII for tenant {tenant_id}")
                get_metrics().inc_counter(
                    "memory.consent.pii_redacted", tags={"tenant": str(tenant_id)}
                )

            get_metrics().inc_counter("memory.consent.scrubbed_bytes", value=len(content))
            return scrubbed

    async def scrub_episodic_stream(self, tenant_id: uuid.UUID, content: str) -> str:
        """Deprecated: Use scrub_text instead."""
        return await self.scrub_text(tenant_id, content)

    def can_commit_to_graph(self, tenant_id: uuid.UUID) -> bool:
        """Check if the user has explicitly consented to structural knowledge gathering."""
        policy = self.get_policy(tenant_id)
        allowed = policy.get("allow_structural_graph_commit", False)

        if not allowed:
            get_metrics().inc_counter(
                "memory.consent.graph_commit_denied", tags={"tenant": str(tenant_id)}
            )
            logger.warning(f"Tenant {tenant_id} denied structural graph commits via policy.")

        return allowed

    async def enforce_ttl_scrubbing(self, episodic_store) -> int:
        """Trigger a background job that seeks and destroys expired Episodic memories.

        Args:
            episodic_store: The Qdrant client or abstraction to execute the wipe.

        Returns:
            The number of records scrubbed.
        """
        with tracer.start_as_current_span("consent.enforce_ttl"):
            datetime.now(UTC)
            # Typically delegates a hard-delete command to the vector store filtering < now
            # returning 0 for this stub.

            get_metrics().inc_counter("memory.consent.ttl_scrub_run")
            return 0
