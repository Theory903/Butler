from __future__ import annotations

from core.envelope import (
    ButlerChannel,
    ButlerEnvelope,
    ButlerEvent,
    EventType,
    OrchestratorResult,
    RiskTier,
)


def test_envelope_derives_multi_tenant_session_identity() -> None:
    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        device_id="dev_android_1",
        channel=ButlerChannel.MOBILE,
        message="Hello Butler",
        gateway={
            "authenticated_user_id": "usr_123",
            "tenant_id": "acct_enterprise_1",
            "assurance_level": "aal2",
        },
    )

    assert envelope.identity is not None
    assert envelope.identity.account_id == "03ab81ad-1849-4985-a69b-73079fdecc63"
    assert envelope.identity.tenant_id == "acct_enterprise_1"
    assert envelope.identity.session_id == "ses_e93b57c13af541c6"
    assert envelope.identity.user_id == "usr_123"
    assert envelope.identity.device_id == "dev_android_1"
    assert envelope.identity.channel == ButlerChannel.MOBILE


def test_orchestrator_result_carries_graph_contract_fields() -> None:
    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        request_id="req_test",
        message="Hello Butler",
    )

    result = OrchestratorResult(
        workflow_id="wf_test",
        session_id=envelope.session_id,
        request_id=envelope.request_id,
        envelope=envelope,
        content="Hello",
        tool_calls=[
            {
                "tool_name": "memory_recall",
                "arguments": {"query": "Hello"},
                "risk_tier": RiskTier.TIER_1_READ,
                "status": "completed",
            }
        ],
        events=[
            ButlerEvent(
                type=EventType.RESPONSE_RENDERED,
                trace_id="trc_test",
                payload={"final": True},
            )
        ],
    )

    assert result.final is True
    assert result.envelope == envelope
    assert result.tool_calls[0].risk_tier == RiskTier.TIER_1_READ
    assert result.events[0].type == EventType.RESPONSE_RENDERED


def test_orchestrator_result_allows_empty_content() -> None:
    result = OrchestratorResult(
        workflow_id="wf_test",
        session_id="ses_e93b57c13af541c6",
        request_id="req_test",
        content="",
    )

    assert result.content == ""


def test_normalize_actions_handles_deterministic_payload() -> None:
    from services.orchestrator.service import _normalize_actions

    raw = [
        {
            "tool_name": "get_time",
            "success": True,
            "data": {"current_time": "2026-04-26T09:07:15+00:00"},
            "execution_id": "abc",
            "verification": {"passed": True},
            "compensation": None,
        }
    ]
    out = _normalize_actions(raw)
    assert len(out) == 1
    assert out[0]["type"] == "get_time"
    assert out[0]["status"] == "completed"
    assert out[0]["payload"]["data"]["current_time"].startswith("2026-04-26")

    result = OrchestratorResult(
        workflow_id="wf_test",
        session_id="ses_e93b57c13af541c6",
        request_id="req_test",
        content="It is 09:07 UTC.",
        actions=out,  # type: ignore[arg-type]
    )
    assert result.actions[0].type == "get_time"
