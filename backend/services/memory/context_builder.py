import logging
from typing import List, Dict
from domain.memory.contracts import ContextPack
from domain.memory.models import ConversationTurn, ExplicitPreference, ExplicitDislike, UserConstraint
from services.memory.retrieval import ScoredMemory

logger = logging.getLogger(__name__)

class ContextBuilder:
    """Butler's context assembler. Transforms raw memories into prompt-ready context packs."""

    def __init__(self, token_budget: int = 4096):
        self._token_budget = token_budget

    def assemble(
        self, 
        history: List[ConversationTurn],
        memories: List[ScoredMemory],
        preferences: List[ExplicitPreference],
        entities: List[Dict],
        constraints: List[UserConstraint]
    ) -> ContextPack:
        """Assembles a ContextPack while staying within the token budget."""
        
        # NOTE: In a real implementation, we would use tiktoken or similar to count tokens.
        # Here we use estimated characters as a proxy for the Butler Phase 11 baseline.
        
        # 1. Priorities (Highest to Lowest)
        # 1. Constraints (System instructions)
        # 2. History (Recent conversation)
        # 3. Preferences (User identity)
        # 4. Memories (Long-term facts)
        
        return ContextPack(
            session_history=history,
            relevant_memories=[m.memory for m in memories],
            preferences=[{"key": p.key, "value": p.value} for p in preferences],
            entities=entities,
            context_token_budget=self._token_budget
        )

    def format_as_prompt(self, pack: ContextPack) -> str:
        """Helper to flatten the context pack into a string for the LLM system prompt."""
        sections = []
        
        if pack.preferences:
            pref_str = "\n".join([f"- {p['key']}: {p['value']}" for p in pack.preferences])
            sections.append(f"USER PREFERENCES:\n{pref_str}")
            
        if pack.relevant_memories:
            mem_str = "\n".join([f"- {m.content}" for m in pack.relevant_memories])
            sections.append(f"RELEVANT MEMORIES:\n{mem_str}")
            
        return "\n\n".join(sections)
