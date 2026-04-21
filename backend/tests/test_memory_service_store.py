from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.memory.evolution import MemoryAction, ReconciledFact
from services.memory.service import MemoryService


@pytest.mark.asyncio
async def test_store_commits_after_struct_write():
    memory_id = uuid.uuid4()
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    query_result = MagicMock()
    memory_entry = SimpleNamespace(id=memory_id, memory_type="episode")
    query_result.scalar_one.return_value = memory_entry
    db.execute = AsyncMock(return_value=query_result)

    evolution = AsyncMock()
    evolution.reconcile.return_value = ReconciledFact(
        action=MemoryAction.CREATE,
        reason="No similar facts found.",
    )

    store = AsyncMock()
    store.write.return_value = SimpleNamespace(entry_id=str(memory_id))

    service = MemoryService(
        db=db,
        redis=AsyncMock(),
        embedder=AsyncMock(),
        retrieval=AsyncMock(),
        evolution=evolution,
        resolution=AsyncMock(),
        understanding=AsyncMock(),
        context_builder=AsyncMock(),
        knowledge_repo=AsyncMock(),
        extraction=AsyncMock(),
        store=store,
        summarizer=AsyncMock(),
        consent_manager=AsyncMock(),
    )

    result = await service.store(
        account_id="00000000-0000-0000-0000-000000000001",
        memory_type="episode",
        content={"note": "persist me"},
        importance=0.5,
    )

    assert result is memory_entry
    db.commit.assert_awaited_once()
