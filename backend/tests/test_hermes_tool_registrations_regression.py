from __future__ import annotations

import importlib
import json

import pytest

from integrations.hermes.tools.registry import registry


def test_get_time_tool_registers_and_dispatches() -> None:
    importlib.import_module("integrations.hermes.tools.get_time_tool")

    payload = json.loads(registry.dispatch("get_time", {}))

    assert "error" not in payload
    assert payload["timezone"] == "UTC"
    assert "The current time is" in payload["content"]


@pytest.mark.asyncio
async def test_web_search_fallback_tool_registers() -> None:
    importlib.import_module("integrations.hermes.tools.a_web_search_fallback")

    entry = registry.get_entry("web_search")

    assert entry is not None
    assert entry.toolset == "web"
    assert entry.is_async is True
