"""Optional LangGraph checkpointer construction."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def build_postgres_checkpointer(connection: Any) -> Any | None:
    """Build a LangGraph Postgres checkpointer when optional deps are installed."""
    if connection is None:
        return None

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        logger.info("langgraph_postgres_checkpointer_unavailable")
        return None

    return PostgresSaver(connection)
