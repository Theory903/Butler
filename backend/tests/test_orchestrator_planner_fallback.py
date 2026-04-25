from __future__ import annotations

import pytest

from services.orchestrator.planner import PlanEngine


@pytest.mark.asyncio
async def test_fallback_plan_for_general_intent_uses_direct_respond_step() -> None:
    planner = PlanEngine(planner_backend=None)

    plan = await planner.create_plan("general", {"prompt": "Hello Butler, how are you today?"})

    assert [step.action for step in plan.steps] == ["respond"]
    assert plan.steps[0].params["message"] == "Hello Butler, how are you today?"


@pytest.mark.asyncio
async def test_fallback_plan_for_time_query_uses_deterministic_get_time() -> None:
    planner = PlanEngine(planner_backend=None)

    plan = await planner.create_plan("general", {"prompt": "what is current time"})

    assert [step.action for step in plan.steps] == ["get_time"]
    assert plan.execution_mode.value == "deterministic"


@pytest.mark.asyncio
async def test_fallback_plan_for_news_query_uses_deterministic_web_search() -> None:
    planner = PlanEngine(planner_backend=None)

    plan = await planner.create_plan(
        "general",
        {"prompt": "news about iran and usa with date"},
    )

    assert [step.action for step in plan.steps] == ["web_search"]
    assert plan.steps[0].params["mode"] == "current_events"
    assert plan.execution_mode.value == "deterministic"
