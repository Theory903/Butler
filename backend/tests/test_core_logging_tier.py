from __future__ import annotations

from core.logging import _dict_to_event
from core.mission_log import Tier
from domain.tools.hermes_compiler import HermesToolCompiler


def test_dict_to_event_falls_back_when_tier_string_is_invalid() -> None:
    event = _dict_to_event(
        {
            "event": "hermes_tool_compiled",
            "message": "compiled",
            "tier": "L0",
        }
    )

    assert event.tier == Tier.NARRATIVE


def test_hermes_compiler_debug_log_uses_risk_tier_field(monkeypatch) -> None:
    compiler = HermesToolCompiler()
    captured: dict[str, object] = {}

    def fake_debug(event: str, **kwargs: object) -> None:
        captured["event"] = event
        captured.update(kwargs)

    monkeypatch.setattr("domain.tools.hermes_compiler.logger.debug", fake_debug)

    compiler.compile("web_search", {"description": "Search web"})

    assert captured["event"] == "hermes_tool_compiled"
    assert captured["risk_tier"] == "L0"
    assert "tier" not in captured
