from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class MemoryAction(Enum):
    CREATE = "create"  # New fact entirely
    REINFORCE = "reinforce"  # Fact already known, increasing confidence/importance
    MERGE = "merge"  # Combine two related facts into one
    SUPERSEDE = "supersede"  # Fact is outdated, replacing with newer version
    CONTRADICT = "contradict"  # Fact conflicts with existing one, needs resolution
    INVALIDATE = "invalidate"  # Fact is proven false


class ReconciledFact(BaseModel):
    action: MemoryAction
    memory_id: str | None = None
    target_memory_id: str | None = None
    confidence_delta: float = 0.0
    reason: str | None = None


class EpisodeCapture(BaseModel):
    session_id: str
    goal: str
    outcome: str
    major_events: list[str]
    lessons_learned: list[str]
    captured_at: datetime
