import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import KnowledgeEntity
from domain.ml.contracts import IReasoningRuntime
from services.memory.knowledge_repo_contract import KnowledgeRepoContract

import structlog

logger = structlog.get_logger(__name__)


class EntityResolutionEngine:
    """Butler's Entity Resolution Engine — resolves mentions to canonical identities."""

    def __init__(
        self,
        db: AsyncSession,
        knowledge_repo: KnowledgeRepoContract,
        ml_runtime: IReasoningRuntime,
    ):
        self._db = db
        self._knowledge_repo = knowledge_repo
        self._ml_runtime = ml_runtime

    async def resolve(
        self, account_id: str, mention: str, context: str | None = None
    ) -> KnowledgeEntity | None:
        """Resolve a name or mention (e.g. 'Steve') to a canonical entity."""
        acc_id = UUID(account_id)

        # 1. Broad Search Strategy
        # Check by exact name match or alias
        existing = await self._knowledge_repo.resolve_identity(acc_id, mention)
        if existing:
            return existing

        # 2. Fuzzy/Semantic Search
        # Fetch top 5 similarly named entities
        candidates = await self._knowledge_repo.search_entities(acc_id, mention, limit=5)
        if not candidates:
            return None

        # 3. LLM-Assisted Disambiguation
        # If multiple candidates or ambiguity exists, use LLM
        prompt = self._build_resolution_prompt(mention, candidates, context)

        try:
            inference_res = await self._ml_runtime.execute_inference(
                profile_name="cloud_fast_general",
                payload={
                    "system": "You are Butler's Entity Resolution Engine. Resolve ambiguous mentions.",
                    "prompt": prompt,
                    "response_format": "json",
                },
            )

            resolution_data = json.loads(inference_res.get("generated_text", "{}"))
            target_id = resolution_data.get("resolved_id")

            if target_id:
                # Return the matching candidate
                for c in candidates:
                    if str(c.id) == target_id:
                        return c

        except Exception as e:
            logger.error(f"Entity resolution inference failed: {e}")

        return None

    def _build_resolution_prompt(
        self, mention: str, candidates: list[KnowledgeEntity], context: str | None
    ) -> str:
        candidates_str = "\n".join(
            [f"- [{c.id}] {c.name} ({c.entity_type}): {c.summary}" for c in candidates]
        )

        return f"""
Resolve the MENTION to one of the CANONICAL ENTITIES.

MENTION: {mention}
CONTEXT: {context or "No context provided."}

CANONICAL ENTITIES:
{candidates_str}

Response format (JSON):
{{
  "resolved_id": "UUID_OF_ENTITY_OR_NULL",
  "reason": "Why this entity matches?"
}}
"""
