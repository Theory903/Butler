from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from services.memory.retrieval import RetrievalFusionEngine


@pytest.mark.asyncio
async def test_calculate_fusion_score_accepts_array_embedding():
    engine = RetrievalFusionEngine(AsyncMock(), AsyncMock(), MagicMock())
    memory = cast(
        Any,
        SimpleNamespace(
            embedding=np.array([0.5, 0.25, 0.0]),
            content="coffee preference",
        ),
    )

    score = await engine._calculate_fusion_score(
        memory=memory,
        query_embedding=[1.0, 0.0, 0.0],
        query="coffee",
        preferences=[],
        dislikes=[],
    )

    assert score["signals"]["semantic"] == 0.5
    assert score["total"] > 0.0
