import logging
import json
from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import MemoryEntry
from domain.memory.evolution import MemoryAction, ReconciledFact
from domain.memory.contracts import IRetrievalEngine
from domain.ml.contracts import IReasoningRuntime

logger = logging.getLogger(__name__)

class MemoryEvolutionEngine:
    """Butler's fact reconciliation and memory evolution engine."""

    def __init__(
        self,
        db: AsyncSession,
        retrieval: IRetrievalEngine,
        ml_runtime: IReasoningRuntime,
    ):
        self._db = db
        self._retrieval = retrieval
        self._ml_runtime = ml_runtime

    async def reconcile(self, account_id: str, new_fact: str, context: Optional[dict] = None) -> ReconciledFact:
        """Decide how to handle a newly observed fact based on existing memory."""
        acc_id = UUID(account_id)
        
        # 1. Fetch similar existing memories for comparison
        similar_memories = await self._retrieval.search(account_id, new_fact, limit=5)
        
        if not similar_memories:
            return ReconciledFact(action=MemoryAction.CREATE, reason="No similar facts found.")

        # 2. Build reconciliation prompt
        # We use a T3 cloud model for high-fidelity reconciliation decisions
        prompt = self._build_reconciliation_prompt(new_fact, similar_memories)
        
        try:
            inference_res = await self._ml_runtime.execute_inference(
                profile_name="cloud_fast_general",
                payload={
                    "system": "You are Butler's Memory Evolution Engine. Reconcile facts.",
                    "prompt": prompt,
                    "response_format": "json"
                }
            )
            
            # NOTE: In our current stub, this returns a simulated response.
            # In a real run, this would be a JSON string from the LLM.
            # We'll parse it safely.
            decision_data = json.loads(inference_res.get("generated_text", "{}"))
            
            action_str = decision_data.get("action", "create").lower()
            return ReconciledFact(
                action=MemoryAction(action_str),
                target_memory_id=decision_data.get("target_id"),
                reason=decision_data.get("reason"),
                confidence_delta=decision_data.get("confidence_delta", 0.0)
            )
            
        except Exception as e:
            logger.error(f"Reconciliation inference failed: {e}")
            return ReconciledFact(action=MemoryAction.CREATE, reason=f"Inference error: {e}")

    def _build_reconciliation_prompt(self, new_fact: str, candidates: list) -> str:
        candidates_str = "\n".join([
            f"- [{c.memory.id}] {c.memory.content} (Confidence: {c.memory.confidence})"
            for c in candidates
        ])
        
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
