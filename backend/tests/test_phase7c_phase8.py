"""Phase 7c + Phase 8 — Policy Gate integration, Cron Service, ACP Server.

Tests:
  Phase 7c:
    1.  Gate step 0 skipped when product_tier=None (backward-compat)
    2.  Gate step 0 passes for allowed capability (PRO + DEFAULT + web_search)
    3.  Gate step 0 blocks file_write on ENTERPRISE + HEALTHCARE profile
    4.  Gate step 0 blocks send_email on PERSONAL + EDUCATION profile
    5.  Gate step 0 passes for tool not in capability map (unmapped tool)
    6.  Gate step 0 blocks external API calls on GOVERNMENT profile
    7.  Tool not in compiled specs raises ToolPolicyViolation (step 1)
    8.  Explicitly blocked spec raises ToolPolicyViolation (step 2)
    9.  Wrong account_tier raises ToolPolicyViolation (step 3)
    10. Wrong channel raises ToolPolicyViolation (step 4)
    11. Insufficient AAL raises AssuranceInsufficient (step 5)
    12. approval_mode=explicit raises ApprovalRequired (step 6)
    13. All steps pass returns spec object

  Phase 8 — CronService:
    14. validate_cron_expression: valid expression passes
    15. validate_cron_expression: wrong field count raises
    16. validate_cron_expression: out-of-range minute raises
    17. validate_cron_expression: step expression valid
    18. validate_cron_expression: list expression valid
    19. create() returns CronJob with correct fields
    20. create() enforces max 50 active jobs per account
    21. create() raises on invalid cron expression
    22. pause() transitions to PAUSED
    23. resume() transitions back to ACTIVE
    24. resume() returns False on non-paused job
    25. delete() removes job
    26. delete() returns False for unknown job
    27. list_jobs() filters by status
    28. record_trigger() increments run_count
    29. record_trigger() auto-expires on max_runs
    30. record_trigger() pauses after error_streak >= 5
    31. expire() sets status to EXPIRED
    32. job_count property

  Phase 8 — ACPServer:
    33. create() returns ACPRequest with PENDING status
    34. create() has correct account_id, tool_name, approval_mode
    35. decide() APPROVED transitions status
    36. decide() DENIED transitions status
    37. decide() returns None for non-existent request
    38. decide() returns None when already decided (idempotent)
    39. decide() returns None when expired
    40. cancel() transitions to CANCELLED
    41. cancel() returns False for non-pending request
    42. get() returns request by ID
    43. list_pending() returns only PENDING requests for account
    44. list_pending() lazily expires timed-out requests
    45. list_all() returns all statuses for account
    46. expire_stale() expires PENDING past expiry
    47. pending_count property
    48. total_count property
    49. await_decision() resolves when decide() called
    50. await_decision() returns TIMED_OUT on timeout
    51. singleton get_acp_server() returns same instance
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

# ── Phase 7c: ButlerToolPolicyGate ────────────────────────────────────────────
from domain.orchestrator.hermes_agent_backend import (
    ApprovalRequired,
    AssuranceInsufficient,
    ButlerToolPolicyGate,
    ToolPolicyViolation,
)
from domain.policy.industry_profiles import IndustryProfile
from domain.policy.product_tiers import ProductTier
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier

# ── Phase 8 ───────────────────────────────────────────────────────────────────
from services.cron.cron_service import (
    ButlerCronService,
    CreateCronJobRequest,
    CronJobStatus,
    CronValidationError,
    validate_cron_expression,
)
from services.workflow.acp_server import (
    ACPDecision,
    ACPStatus,
    ButlerACPServer,
    get_acp_server,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_spec(
    name: str = "web_search",
    blocked: bool = False,
    block_reason: str = "",
    visible_tiers: list | None = None,
    visible_channels: list | None = None,
    min_assurance_level: str = "AAL1",
    approval_mode: str = "none",
    risk_tier: RiskTier = RiskTier.L0,
) -> ButlerToolSpec:
    return ButlerToolSpec(
        name=name,
        hermes_name=name,
        risk_tier=risk_tier,
        blocked=blocked,
        block_reason=block_reason,
        visible_tiers=visible_tiers or ["*"],
        visible_channels=visible_channels or ["*"],
        min_assurance_level=min_assurance_level,
        approval_mode=approval_mode,
        has_compensation=False,
        sandbox_profile="none",
    )


def _gate(
    tool_name: str = "web_search",
    product_tier=None,
    industry_profile=None,
    account_tier: str = "*",
    channel: str = "api",
    assurance_level: str = "AAL1",
    blocked: bool = False,
    visible_tiers: list | None = None,
    visible_channels: list | None = None,
    approval_mode: str = "none",
    min_assurance_level: str = "AAL1",
    extra_tools: dict | None = None,
) -> ButlerToolPolicyGate:
    spec = _make_spec(
        name=tool_name,
        blocked=blocked,
        visible_tiers=visible_tiers or ["*"],
        visible_channels=visible_channels or ["*"],
        approval_mode=approval_mode,
        min_assurance_level=min_assurance_level,
    )
    specs = {tool_name: spec}
    if extra_tools:
        specs.update(extra_tools)
    return ButlerToolPolicyGate(
        compiled_specs=specs,
        account_tier=account_tier,
        channel=channel,
        assurance_level=assurance_level,
        product_tier=product_tier,
        industry_profile=industry_profile,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7c: ButlerToolPolicyGate
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerToolPolicyGatePhase7c:
    def test_step0_skipped_when_product_tier_none(self):
        """Backward-compat: no product_tier → step 0 is skipped entirely."""
        gate = _gate("web_search", product_tier=None, industry_profile=None)
        spec = gate.check("web_search", {})
        assert spec.name == "web_search"

    def test_step0_passes_allowed_capability(self):
        """PRO + DEFAULT profile allows web_search."""
        gate = _gate(
            "web_search",
            product_tier=ProductTier.PRO,
            industry_profile=IndustryProfile.DEFAULT,
        )
        spec = gate.check("web_search", {})
        assert spec.name == "web_search"

    def test_step0_blocks_file_write_healthcare(self):
        """Healthcare profile restricts file_write."""
        gate = _gate(
            "file_write",
            product_tier=ProductTier.ENTERPRISE,
            industry_profile=IndustryProfile.HEALTHCARE,
        )
        with pytest.raises(ToolPolicyViolation) as exc_info:
            gate.check("file_write", {})
        assert "file_write" in str(exc_info.value)

    def test_step0_blocks_email_send_education(self):
        """Education profile restricts email_send."""
        gate = _gate(
            "send_email",
            product_tier=ProductTier.PERSONAL,
            industry_profile=IndustryProfile.EDUCATION,
        )
        with pytest.raises(ToolPolicyViolation):
            gate.check("send_email", {})

    def test_step0_passes_unmapped_tool(self):
        """Tools not in _TOOL_CAPABILITY_MAP skip step 0 (no restriction)."""
        gate = _gate(
            "some_custom_tool",
            product_tier=ProductTier.PERSONAL,
            industry_profile=IndustryProfile.EDUCATION,
            extra_tools={"some_custom_tool": _make_spec("some_custom_tool")},
        )
        spec = gate.check("some_custom_tool", {})
        assert spec.name == "some_custom_tool"

    def test_step0_blocks_external_api_government(self):
        """Government profile restricts external_api_calls."""
        gate = _gate(
            "http_get",
            product_tier=ProductTier.ENTERPRISE,
            industry_profile=IndustryProfile.GOVERNMENT,
            extra_tools={"http_get": _make_spec("http_get")},
        )
        with pytest.raises(ToolPolicyViolation):
            gate.check("http_get", {})

    def test_step1_unknown_tool_raises(self):
        gate = _gate("web_search")
        with pytest.raises(ToolPolicyViolation) as exc_info:
            gate.check("ghost_tool", {})
        assert "not in Butler" in str(exc_info.value)

    def test_step2_blocked_spec_raises(self):
        gate = _gate("web_search", blocked=True)
        with pytest.raises(ToolPolicyViolation) as exc_info:
            gate.check("web_search", {})
        assert "FORBIDDEN" in str(exc_info.value)

    def test_step3_wrong_tier_raises(self):
        gate = _gate(
            "web_search",
            account_tier="basic",
            visible_tiers=["pro", "enterprise"],
        )
        with pytest.raises(ToolPolicyViolation) as exc_info:
            gate.check("web_search", {})
        assert "account tier" in str(exc_info.value).lower()

    def test_step4_wrong_channel_raises(self):
        gate = _gate(
            "web_search",
            channel="sms",
            visible_channels=["api", "web"],
        )
        with pytest.raises(ToolPolicyViolation) as exc_info:
            gate.check("web_search", {})
        assert "channel" in str(exc_info.value).lower()

    def test_step5_insufficient_aal_raises(self):
        gate = _gate(
            "web_search",
            assurance_level="AAL1",
            min_assurance_level="AAL3",
        )
        with pytest.raises(AssuranceInsufficient) as exc_info:
            gate.check("web_search", {})
        assert "AAL3" in str(exc_info.value)

    def test_step6_approval_required_raises(self):
        gate = _gate("web_search", approval_mode="explicit")
        with pytest.raises(ApprovalRequired) as exc_info:
            gate.check("web_search", {})
        assert exc_info.value.tool_name == "web_search"

    def test_full_pass_returns_spec(self):
        gate = _gate("web_search")
        spec = gate.check("web_search", {})
        assert isinstance(spec, ButlerToolSpec)
        assert spec.name == "web_search"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: ButlerCronService
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerCronService:
    def _svc(self) -> ButlerCronService:
        return ButlerCronService()

    def _req(self, account_id: str = "acc1", cron: str = "0 9 * * *") -> CreateCronJobRequest:
        return CreateCronJobRequest(
            account_id=account_id,
            name="Morning reminder",
            cron_expression=cron,
            action="send_notification",
            payload={"message": "Good morning"},
        )

    # ── Cron expression validation ────────────────────────────────────────────

    def test_valid_cron_passes(self):
        assert validate_cron_expression("0 9 * * *") is True

    def test_valid_cron_with_range(self):
        assert validate_cron_expression("0 9 * * 1-5") is True

    def test_valid_cron_with_step(self):
        assert validate_cron_expression("*/15 * * * *") is True

    def test_valid_cron_with_list(self):
        assert validate_cron_expression("0 9,17 * * *") is True

    def test_cron_wrong_field_count_raises(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("0 9 *")

    def test_cron_out_of_range_minute_raises(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("61 9 * * *")

    def test_cron_out_of_range_hour_raises(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("0 25 * * *")

    def test_cron_invalid_step_raises(self):
        with pytest.raises(CronValidationError):
            validate_cron_expression("*/0 * * * *")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def test_create_returns_job(self):
        svc = self._svc()
        job = svc.create(self._req())
        assert job.id is not None
        assert job.status == CronJobStatus.ACTIVE
        assert job.account_id == "acc1"
        assert job.run_count == 0

    def test_create_invalid_cron_raises(self):
        svc = self._svc()
        with pytest.raises(CronValidationError):
            svc.create(self._req(cron="bad cron"))

    def test_create_enforces_50_job_limit(self):
        svc = self._svc()
        for i in range(50):
            svc.create(
                CreateCronJobRequest(
                    account_id="acc_limit",
                    name=f"job_{i}",
                    cron_expression="0 9 * * *",
                    action="noop",
                )
            )
        with pytest.raises(ValueError, match="maximum"):
            svc.create(
                CreateCronJobRequest(
                    account_id="acc_limit",
                    name="one_too_many",
                    cron_expression="0 9 * * *",
                    action="noop",
                )
            )

    def test_pause_transitions_status(self):
        svc = self._svc()
        job = svc.create(self._req())
        assert svc.pause(job.id) is True
        assert svc.get(job.id).status == CronJobStatus.PAUSED

    def test_resume_transitions_back_to_active(self):
        svc = self._svc()
        job = svc.create(self._req())
        svc.pause(job.id)
        assert svc.resume(job.id) is True
        assert svc.get(job.id).status == CronJobStatus.ACTIVE

    def test_resume_not_paused_returns_false(self):
        svc = self._svc()
        job = svc.create(self._req())
        assert svc.resume(job.id) is False  # Already ACTIVE, not PAUSED

    def test_delete_removes_job(self):
        svc = self._svc()
        job = svc.create(self._req())
        assert svc.delete(job.id) is True
        assert svc.get(job.id) is None

    def test_delete_unknown_returns_false(self):
        svc = self._svc()
        assert svc.delete("nonexistent_id") is False

    def test_list_jobs_filter_by_status(self):
        svc = self._svc()
        j1 = svc.create(self._req())
        svc.create(self._req())
        svc.pause(j1.id)
        paused = svc.list_jobs("acc1", status=CronJobStatus.PAUSED)
        assert len(paused) == 1
        assert paused[0].id == j1.id

    def test_record_trigger_increments_count(self):
        svc = self._svc()
        job = svc.create(self._req())
        svc.record_trigger(job.id, success=True)
        assert svc.get(job.id).run_count == 1

    def test_record_trigger_auto_expires_on_max_runs(self):
        svc = self._svc()
        req = CreateCronJobRequest(
            account_id="acc1",
            name="j",
            cron_expression="0 9 * * *",
            action="noop",
            max_runs=2,
        )
        job = svc.create(req)
        svc.record_trigger(job.id, success=True)
        svc.record_trigger(job.id, success=True)
        assert svc.get(job.id).status == CronJobStatus.EXPIRED

    def test_record_trigger_auto_fails_on_error_streak(self):
        svc = self._svc()
        job = svc.create(self._req())
        for _ in range(5):
            svc.record_trigger(job.id, success=False)
        assert svc.get(job.id).status == CronJobStatus.FAILED

    def test_expire_sets_expired_status(self):
        svc = self._svc()
        job = svc.create(self._req())
        svc.expire(job.id)
        assert svc.get(job.id).status == CronJobStatus.EXPIRED

    def test_job_count_property(self):
        svc = self._svc()
        svc.create(self._req("a1"))
        svc.create(self._req("a2"))
        assert svc.job_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: ButlerACPServer
# ─────────────────────────────────────────────────────────────────────────────


class TestButlerACPServer:
    def _server(self) -> ButlerACPServer:
        return ButlerACPServer()

    def _create(self, server: ButlerACPServer, account_id: str = "acc1"):
        return server.create(
            account_id=account_id,
            tool_name="send_email",
            approval_mode="explicit",
            risk_tier="L2",
            description="Send email to team",
            task_id="task_1",
            session_id="sess_1",
        )

    def test_create_returns_pending_request(self):
        server = self._server()
        req = self._create(server)
        assert req.status == ACPStatus.PENDING
        assert req.request_id is not None

    def test_create_correct_fields(self):
        server = self._server()
        req = self._create(server, account_id="user123")
        assert req.account_id == "user123"
        assert req.tool_name == "send_email"
        assert req.approval_mode == "explicit"

    def test_decide_approved_transitions_status(self):
        server = self._server()
        req = self._create(server)
        result = server.decide(req.request_id, ACPDecision.APPROVED, human_id="human_42")
        assert result is not None
        assert result.decision == ACPDecision.APPROVED
        assert server.get(req.request_id).status == ACPStatus.APPROVED

    def test_decide_denied_transitions_status(self):
        server = self._server()
        req = self._create(server)
        server.decide(req.request_id, ACPDecision.DENIED, human_id="human_42")
        assert server.get(req.request_id).status == ACPStatus.DENIED

    def test_decide_unknown_request_returns_none(self):
        server = self._server()
        result = server.decide("ghost_id", ACPDecision.APPROVED, human_id="h1")
        assert result is None

    def test_decide_already_decided_idempotent(self):
        server = self._server()
        req = self._create(server)
        server.decide(req.request_id, ACPDecision.APPROVED, human_id="h1")
        result = server.decide(req.request_id, ACPDecision.APPROVED, human_id="h1")
        assert result is None  # Already decided

    def test_decide_expired_request_returns_none(self):
        server = self._server()
        req = server.create(
            account_id="acc1",
            tool_name="send_email",
            approval_mode="explicit",
            risk_tier="L2",
            description="test",
            ttl_hours=0,  # Already expired
        )
        # Backdated expiry
        from datetime import timedelta

        req.expires_at = req.created_at - timedelta(hours=1)
        result = server.decide(req.request_id, ACPDecision.APPROVED, human_id="h1")
        assert result is None

    def test_cancel_transitions_to_cancelled(self):
        server = self._server()
        req = self._create(server)
        assert server.cancel(req.request_id) is True
        assert server.get(req.request_id).status == ACPStatus.CANCELLED

    def test_cancel_non_pending_returns_false(self):
        server = self._server()
        req = self._create(server)
        server.decide(req.request_id, ACPDecision.APPROVED, human_id="h1")
        assert server.cancel(req.request_id) is False

    def test_get_returns_request(self):
        server = self._server()
        req = self._create(server)
        assert server.get(req.request_id) is req

    def test_list_pending_only_pending(self):
        server = self._server()
        r1 = self._create(server)
        r2 = self._create(server)
        server.decide(r1.request_id, ACPDecision.DENIED, human_id="h1")
        pending = server.list_pending("acc1")
        assert len(pending) == 1
        assert pending[0].request_id == r2.request_id

    def test_list_pending_lazy_expires(self):
        server = self._server()
        req = self._create(server)
        req.expires_at = datetime.now(UTC) - timedelta(hours=1)
        pending = server.list_pending("acc1")
        assert len(pending) == 0
        assert server.get(req.request_id).status == ACPStatus.TIMED_OUT

    def test_list_all_includes_all_statuses(self):
        server = self._server()
        r1 = self._create(server)
        self._create(server)
        server.decide(r1.request_id, ACPDecision.APPROVED, human_id="h1")
        all_reqs = server.list_all("acc1")
        assert len(all_reqs) == 2

    def test_expire_stale_returns_count(self):
        server = self._server()
        req = self._create(server)
        req.expires_at = datetime.now(UTC) - timedelta(hours=1)
        count = server.expire_stale()
        assert count == 1

    def test_pending_count_property(self):
        server = self._server()
        self._create(server)
        self._create(server)
        assert server.pending_count == 2

    def test_total_count_property(self):
        server = self._server()
        self._create(server)
        assert server.total_count == 1

    def test_await_decision_resolves_on_decide(self):
        server = self._server()
        req = self._create(server)

        async def _run():
            async def _decider():
                await asyncio.sleep(0.05)
                server.decide(req.request_id, ACPDecision.APPROVED, human_id="h1")

            task = asyncio.create_task(_decider())
            decision = await server.await_decision(req.request_id, timeout_s=2.0)
            await task
            return decision

        decision = asyncio.run(_run())
        assert decision == ACPDecision.APPROVED

    def test_await_decision_returns_timed_out_on_timeout(self):
        server = self._server()
        req = self._create(server)

        async def _run():
            return await server.await_decision(req.request_id, timeout_s=0.05)

        decision = asyncio.run(_run())
        assert decision == ACPDecision.TIMED_OUT

    def test_singleton_returns_same_instance(self):
        # Reset for test isolation
        import services.workflow.acp_server as mod

        mod._acp_server = None
        s1 = get_acp_server()
        s2 = get_acp_server()
        assert s1 is s2
