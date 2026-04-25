import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.contracts import IRetrievalEngine
from domain.memory.evolution import MemoryAction, ReconciledFact
from domain.ml.contracts import IReasoningRuntime

if TYPE_CHECKING:
    from services.memory.consent_manager import ConsentManager

logger = logging.getLogger(__name__)


class MemoryEvolutionEngine:
    """Butler's fact reconciliation and memory evolution engine."""

    def __init__(
        self,
        db: AsyncSession,
        retrieval: IRetrievalEngine,
        ml_runtime: IReasoningRuntime,
        consent_manager: "ConsentManager | None" = None,
    ):
        self._db = db
        self._retrieval = retrieval
        self._ml_runtime = ml_runtime
        self._consent = consent_manager

    async def reconcile(
        self, account_id: str, new_fact: str, context: dict | None = None
    ) -> ReconciledFact:
        """Decide how to handle a newly observed fact based on existing memory.

        Enhanced with:
        - Better fallback logic when ML runtime fails
        - Confidence-based action thresholds
        - Temporal decay consideration for existing memories
        - Improved prompt engineering
        """
        acc_id = UUID(account_id)

        if self._consent is not None:
            new_fact = await self._consent.scrub_text(acc_id, new_fact)

        # 1. Fetch similar existing memories for comparison
        similar_memories = await self._retrieval.search(account_id, new_fact, limit=5)

        if not similar_memories:
            return ReconciledFact(action=MemoryAction.CREATE, reason="No similar facts found.")

        # 2. Apply temporal decay to existing memory scores
        # Recent memories are more likely to be accurate
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        decayed_memories = []
        for scored_mem in similar_memories:
            if scored_mem.memory.created_at:
                days_old = (now - scored_mem.memory.created_at).days
                # Exponential decay: 0.95^days
                decay_factor = 0.95 ** min(days_old, 30)  # Cap at 30 days
                scored_mem.score *= decay_factor
            decayed_memories.append(scored_mem)

        # Sort by decayed scores
        decayed_memories.sort(key=lambda x: x.score, reverse=True)

        # 3. Build reconciliation prompt with improved engineering
        prompt = self._build_reconciliation_prompt(new_fact, decayed_memories)

        try:
            inference_res = await self._ml_runtime.execute_inference(
                profile_name="cloud_fast_general",
                payload={
                    "system": self._build_system_prompt(),
                    "prompt": prompt,
                    "response_format": "json",
                },
            )

            decision_data = json.loads(inference_res.get("generated_text", "{}"))

            action_str = decision_data.get("action", "create").lower()

            # Validate action
            valid_actions = ["reinforce", "merge", "supersede", "contradict", "create"]
            if action_str not in valid_actions:
                action_str = "create"
                logger.warning(f"Invalid action '{action_str}', defaulting to CREATE")

            # Confidence delta validation
            conf_delta = decision_data.get("confidence_delta", 0.0)
            if not isinstance(conf_delta, (int, float)) or abs(conf_delta) > 1.0:
                conf_delta = 0.0

            return ReconciledFact(
                action=MemoryAction(action_str),
                target_memory_id=decision_data.get("target_id"),
                reason=decision_data.get("reason", ""),
                confidence_delta=conf_delta,
            )

        except Exception as e:
            logger.error(f"Reconciliation inference failed: {e}")
            # Fallback: rule-based reconciliation
            return self._fallback_reconciliation(new_fact, decayed_memories)

    def _build_system_prompt(self) -> str:
        """Build improved system prompt for memory evolution."""
        return """You are Butler's Memory Evolution Engine. Your task is to reconcile new facts with existing memories.

PRINCIPLES:
1. Prefer precision: Only merge if the new fact adds specific, non-redundant detail
2. Respect temporality: Newer facts are more likely to be accurate
3. Avoid contradictions: Flag conflicts for human review when uncertain
4. Maintain confidence: Only reduce confidence if there's clear evidence against a fact

ACTION CATEGORIES:
- REINFORCE: New fact confirms existing memory without changes. Increase confidence slightly.
- MERGE: New fact adds complementary detail to existing memory. Combine both.
- SUPERSEDE: New fact is a newer/updated version that replaces old information.
- CONTRADICT: New fact conflicts with existing memory. Flag for resolution.
- CREATE: New fact is unrelated to existing memories. Create new entry.

Respond with a JSON object containing action, target_id (if applicable), reason, and confidence_delta (-0.2 to +0.2)."""

    def _fallback_reconciliation(self, new_fact: str, similar_memories: list) -> ReconciledFact:
        """Rule-based reconciliation when ML runtime fails."""
        if not similar_memories:
            return ReconciledFact(
                action=MemoryAction.CREATE, reason="No similar memories (fallback)"
            )

        # Simple similarity-based fallback
        top_match = similar_memories[0]

        if top_match.score > 0.9:
            # Very high similarity: reinforce
            return ReconciledFact(
                action=MemoryAction.REINFORCE,
                target_memory_id=str(top_match.memory.id),
                reason=f"High similarity ({top_match.score:.2f}) - reinforce (fallback)",
                confidence_delta=0.1,
            )
        if top_match.score > 0.7:
            # High similarity: merge
            return ReconciledFact(
                action=MemoryAction.MERGE,
                target_memory_id=str(top_match.memory.id),
                reason=f"Moderate similarity ({top_match.score:.2f}) - merge (fallback)",
                confidence_delta=0.05,
            )
        # Low similarity: create new
        return ReconciledFact(
            action=MemoryAction.CREATE,
            reason=f"Low similarity ({top_match.score:.2f}) - create new (fallback)",
        )

    def _build_reconciliation_prompt(self, new_fact: str, candidates: list) -> str:
        candidates_str = "\n".join(
            [
                f"- [{c.memory.id}] {c.memory.content} (Confidence: {c.memory.confidence})"
                for c in candidates
            ]
        )

        return f"""
Analyze the RELATIONSHIP between the NEW FACT and the EXISTING MEMORIES.

NEW FACT: {new_fact}

EXISTING MEMORIES:
{candidates_str}

ACTION CATEGORIES:
1. REINFORCE: New fact confirms existing memory without changes.
2. MERGE: New fact adds detail to existing memory.
3. SUPERSEDE: New fact is a newer/updated version of existing memory.
4. CONTRADICT: New fact conflicts with existing memory and needs resolution.
5. CREATE: New fact is unrelated to existing memories.

Response format (JSON):
{{
  "action": "ACTION_CATEGORY",
  "target_id": "UUID_OF_EXISTING_MEMORY_IF_APPLICABLE",
  "reason": "BRIEF_RATIONALE",
  "confidence_delta": 0.1
}}
"""
