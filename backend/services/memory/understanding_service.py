import logging
import json
from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from domain.memory.models import ExplicitPreference, ExplicitDislike, UserConstraint
from domain.ml.contracts import IReasoningRuntime
from services.memory.knowledge_repo_contract import KnowledgeRepoContract

logger = logging.getLogger(__name__)

class UnderstandingService:
    """Butler's User Understanding Layer — extracts preferences, dislikes, and constraints."""

    def __init__(
        self,
        db: AsyncSession,
        ml_runtime: IReasoningRuntime,
        knowledge_repo: Optional[KnowledgeRepoContract] = None,
    ):
        self._db = db
        self._ml_runtime = ml_runtime
        self._knowledge_repo = knowledge_repo

    async def analyze_turn(self, account_id: str, role: str, content: str) -> None:
        """Analyze a single conversation turn for potential identity/preference updates."""
        if role != "user":
            return

        acc_id = UUID(account_id)
        
        # We use a fast T2 or T3 model to extract latent preferences
        prompt = f"""
Analyze the USER MESSAGE for Explicit Preferences, Dislikes, or Constraints.

MESSAGE: "{content}"

Response format (JSON):
{{
  "preferences": [
    {{"category": "food", "key": "coffee", "value": "black", "confidence": 0.9}}
  ],
  "dislikes": [
    {{"key": "mushrooms", "reason": "texture", "confidence": 0.8}}
  ],
  "constraints": [
    {{"type": "communication", "value": "no emojis", "active": true}}
  ]
}}
Only return items if they are EXPLICIT or strongly implied.
"""

        try:
            inference_res = await self._ml_runtime.execute_inference(
                profile_name="cloud_fast_general",
                payload={
                    "system": "You are Butler's User Understanding Engine.",
                    "prompt": prompt,
                    "response_format": "json"
                }
            )
            
            signals = json.loads(inference_res.get("generated_text", "{}"))
            
            # 1. Update Preferences
            for pref in signals.get("preferences", []):
                await self._upsert_preference(acc_id, pref)
                
            # 2. Update Dislikes
            for dislike in signals.get("dislikes", []):
                await self._upsert_dislike(acc_id, dislike)
                
            # 3. Update Constraints
            for constraint in signals.get("constraints", []):
                await self._upsert_constraint(acc_id, constraint)
                
            await self._db.commit()
            
        except Exception as e:
            logger.error(f"User understanding analysis failed: {e}")

    async def _upsert_preference(self, account_id: UUID, data: dict):
        stmt = select(ExplicitPreference).where(
            ExplicitPreference.account_id == account_id,
            ExplicitPreference.key == data["key"]
        )
        res = await self._db.execute(stmt)
        pref = res.scalar_one_or_none()
        
        if pref:
            pref.value = data["value"]
            pref.confidence = data["confidence"]
        else:
            pref = ExplicitPreference(
                account_id=account_id,
                category=data["category"],
                key=data["key"],
                value=data["value"],
                confidence=data["confidence"]
            )
            self._db.add(pref)
        
        # Sync to Neo4j Graph
        if self._knowledge_repo:
            await self._knowledge_repo.upsert_entity(
                account_id=account_id,
                entity_type="PREFERENCE",
                name=f"Pref: {data['key']}",
                summary=f"User preference for {data['key']} is {data['value']}",
                metadata={"category": data["category"], "confidence": data["confidence"]}
            )

    async def _upsert_dislike(self, account_id: UUID, data: dict):
        stmt = select(ExplicitDislike).where(
            ExplicitDislike.account_id == account_id,
            ExplicitDislike.key == data["key"]
        )
        res = await self._db.execute(stmt)
        dis = res.scalar_one_or_none()
        
        if dis:
            dis.reason = data.get("reason")
            dis.confidence = data["confidence"]
        else:
            dis = ExplicitDislike(
                account_id=account_id,
                key=data["key"],
                reason=data.get("reason"),
                confidence=data["confidence"]
            )
            self._db.add(dis)

    async def _upsert_constraint(self, account_id: UUID, data: dict):
        stmt = select(UserConstraint).where(
            UserConstraint.account_id == account_id,
            UserConstraint.constraint_type == data["type"]
        )
        res = await self._db.execute(stmt)
        con = res.scalar_one_or_none()
        
        if con:
            con.value = data["value"]
            con.active = data.get("active", True)
        else:
            con = UserConstraint(
                account_id=account_id,
                constraint_type=data["type"],
                value=data["value"],
                active=data.get("active", True)
            )
            self._db.add(con)
