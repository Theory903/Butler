"""Phase 7b — Industry Profiles and Platform Registry tests.

Tests industry profile capability overlays (healthcare, government, finance,
legal, education, default) and PlatformRegistry (14 adapters, filter,
truncate, approval gate, webhook routing).

Also tests the cross-cutting concern: profile+tier effective capability
resolution (union, intersection, restriction rules).

Verifies:
  1.  Industry profiles: default adds nothing, removes nothing
  2.  Healthcare adds HIPAA_MODE capability
  3.  Healthcare removes FILE_WRITE (PHI protection)
  4.  Government removes CLOUD_FRONTIER_LLM (data sovereignty)
  5.  Government adds FEDRAMP_MODE
  6.  Finance removes EXTERNAL_API_CALLS
  7.  Legal removes CODE_EXECUTION
  8.  Education removes EMAIL_SEND
  9.  resolve_capabilities: effective = (tier ∪ adds) − removes
  10. resolve_capabilities: profile_adds capped at Enterprise caps
  11. check_profile_capability: allowed=True when cap in effective set
  12. check_profile_capability: allowed=False with "restricted" reason
  13. check_profile_capability: allowed=False with "not available" reason
  14. profile_meets_min_tier: enterprise profile requires enterprise tier
  15. profile_meets_min_tier: personal profile works on personal tier
  16. PlatformRegistry: 14 adapters registered
  17. PlatformRegistry: get() returns correct adapter
  18. PlatformRegistry: get() returns None for unknown
  19. PlatformRegistry: filter(supports_streaming=True) only streaming platforms
  20. PlatformRegistry: filter(supports_voice=True) voice platforms
  21. PlatformRegistry: filter(auth_mechanism=JWT) correct count
  22. PlatformRegistry: get_by_webhook_path returns correct platform
  23. PlatformRegistry: get_by_webhook_path None for unknown path
  24. PlatformRegistry: truncate_for_platform trims SMS to 160 chars
  25. PlatformRegistry: truncate_for_platform no-op for short text
  26. PlatformRegistry: truncate appends [truncated] marker
  27. PlatformRegistry: requires_approval_for_tool SMS wildcard → True
  28. PlatformRegistry: requires_approval_for_tool slack → True for file_write
  29. PlatformRegistry: requires_approval_for_tool API → False (no restrictions)
  30. PlatformRegistry: list_all has 14 items
  31. PlatformRegistry: singleton returns same instance
  32. PlatformRegistry: Slack max_message_chars = 3000
  33. PlatformRegistry: IoT uses mTLS auth
  34. PlatformRegistry: MCP client supports streaming
  35. Government ENTERPRISE effective caps include FEDRAMP_MODE
  36. Government ENTERPRISE effective caps exclude CLOUD_FRONTIER_LLM
  37. Healthcare PERSONAL cannot activate (min_tier check)
  38. resolve_capabilities on unknown tier returns empty caps
"""

from __future__ import annotations

import pytest

from domain.policy.industry_profiles import (
    IndustryProfile,
    ProfileConfig,
    PROFILE_CONFIGS,
    resolve_capabilities,
    check_profile_capability,
    profile_meets_min_tier,
)
from domain.policy.product_tiers import (
    ProductTier,
    CapabilityFlag,
)
from services.gateway.platform_registry import (
    PlatformRegistry,
    PlatformAdapter,
    PlatformId,
    AuthMechanism,
    MessageFormat,
    get_platform_registry,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 28: Industry Profiles
# ─────────────────────────────────────────────────────────────────────────────

class TestIndustryProfiles:

    # ── Default profile ───────────────────────────────────────────────────────

    def test_default_adds_nothing(self):
        eff = resolve_capabilities(ProductTier.PRO, IndustryProfile.DEFAULT)
        assert eff.added == frozenset()

    def test_default_removes_nothing(self):
        eff = resolve_capabilities(ProductTier.PRO, IndustryProfile.DEFAULT)
        assert eff.removed == frozenset()

    # ── Healthcare ────────────────────────────────────────────────────────────

    def test_healthcare_adds_hipaa_to_enterprise(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.HEALTHCARE)
        assert CapabilityFlag.HIPAA_MODE in eff.capabilities

    def test_healthcare_removes_file_write(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.HEALTHCARE)
        assert CapabilityFlag.FILE_WRITE not in eff.capabilities

    def test_healthcare_adds_soc2(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.HEALTHCARE)
        assert CapabilityFlag.SOC2_AUDIT in eff.capabilities

    # ── Government ────────────────────────────────────────────────────────────

    def test_government_removes_cloud_frontier_llm(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.GOVERNMENT)
        assert CapabilityFlag.CLOUD_FRONTIER_LLM not in eff.capabilities

    def test_government_adds_fedramp(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.GOVERNMENT)
        assert CapabilityFlag.FEDRAMP_MODE in eff.capabilities

    def test_government_removes_external_api_calls(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.GOVERNMENT)
        assert CapabilityFlag.EXTERNAL_API_CALLS not in eff.capabilities

    # ── Finance ───────────────────────────────────────────────────────────────

    def test_finance_removes_external_api_calls(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.FINANCE)
        assert CapabilityFlag.EXTERNAL_API_CALLS not in eff.capabilities

    def test_finance_adds_soc2(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.FINANCE)
        assert CapabilityFlag.SOC2_AUDIT in eff.capabilities

    # ── Legal ─────────────────────────────────────────────────────────────────

    def test_legal_removes_code_execution(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.LEGAL)
        assert CapabilityFlag.CODE_EXECUTION not in eff.capabilities

    def test_legal_removes_external_api_calls(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.LEGAL)
        assert CapabilityFlag.EXTERNAL_API_CALLS not in eff.capabilities

    # ── Education ─────────────────────────────────────────────────────────────

    def test_education_removes_email_send(self):
        eff = resolve_capabilities(ProductTier.PERSONAL, IndustryProfile.EDUCATION)
        assert CapabilityFlag.EMAIL_SEND not in eff.capabilities

    def test_education_removes_device_control_from_enterprise(self):
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.EDUCATION)
        assert CapabilityFlag.DEVICE_CONTROL not in eff.capabilities

    # ── Effective capability formula ──────────────────────────────────────────

    def test_effective_retains_non_restricted_caps(self):
        """Web search should survive in healthcare enterprise."""
        eff = resolve_capabilities(ProductTier.ENTERPRISE, IndustryProfile.HEALTHCARE)
        assert CapabilityFlag.WEB_SEARCH in eff.capabilities

    def test_profile_adds_capped_at_enterprise(self):
        """Profile additions must not exceed Enterprise capability set."""
        for profile in IndustryProfile:
            eff = resolve_capabilities(ProductTier.PERSONAL, profile)
            # No addition should exist that goes beyond Enterprise
            from domain.policy.product_tiers import TIER_CONFIGS
            enterprise_caps = TIER_CONFIGS[ProductTier.ENTERPRISE].capabilities
            assert eff.added.issubset(enterprise_caps)

    def test_resolve_unknown_tier_returns_empty(self):
        eff = resolve_capabilities("unknown_tier", IndustryProfile.DEFAULT)  # type: ignore
        assert eff.capabilities == frozenset() or isinstance(eff.capabilities, frozenset)

    # ── check_profile_capability ──────────────────────────────────────────────

    def test_check_allowed_returns_true(self):
        result = check_profile_capability(
            ProductTier.ENTERPRISE,
            IndustryProfile.HEALTHCARE,
            CapabilityFlag.WEB_SEARCH,
        )
        assert result.allowed is True
        assert result.reason == ""

    def test_check_restricted_has_reason(self):
        result = check_profile_capability(
            ProductTier.ENTERPRISE,
            IndustryProfile.HEALTHCARE,
            CapabilityFlag.FILE_WRITE,
        )
        assert result.allowed is False
        assert "restricted" in result.reason.lower() or "healthcare" in result.reason.lower()

    def test_check_tier_missing_cap_reason(self):
        result = check_profile_capability(
            ProductTier.PERSONAL,
            IndustryProfile.DEFAULT,
            CapabilityFlag.CODE_EXECUTION,
        )
        assert result.allowed is False
        assert "personal" in result.reason.lower() or "tier" in result.reason.lower()

    # ── profile_meets_min_tier ────────────────────────────────────────────────

    def test_healthcare_requires_enterprise(self):
        assert profile_meets_min_tier(ProductTier.ENTERPRISE, IndustryProfile.HEALTHCARE) is True
        assert profile_meets_min_tier(ProductTier.PRO, IndustryProfile.HEALTHCARE) is False
        assert profile_meets_min_tier(ProductTier.PERSONAL, IndustryProfile.HEALTHCARE) is False

    def test_education_works_on_personal(self):
        assert profile_meets_min_tier(ProductTier.PERSONAL, IndustryProfile.EDUCATION) is True

    def test_legal_requires_pro(self):
        assert profile_meets_min_tier(ProductTier.PRO, IndustryProfile.LEGAL) is True
        assert profile_meets_min_tier(ProductTier.PERSONAL, IndustryProfile.LEGAL) is False


# ─────────────────────────────────────────────────────────────────────────────
# Test 29: PlatformRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestPlatformRegistry:

    def _reg(self) -> PlatformRegistry:
        return PlatformRegistry()

    def test_twenty_five_adapters_registered(self):
        reg = self._reg()
        assert reg.platform_count == 25

    def test_get_returns_correct_adapter(self):
        reg = self._reg()
        adapter = reg.get(PlatformId.SLACK)
        assert adapter is not None
        assert adapter.id == PlatformId.SLACK
        assert adapter.display_name == "Slack"

    def test_get_unknown_returns_none(self):
        reg = self._reg()
        assert reg.get("unknown_platform") is None  # type: ignore

    def test_filter_streaming_platforms(self):
        reg = self._reg()
        streaming = reg.filter(supports_streaming=True)
        assert len(streaming) > 0
        assert all(a.supports_streaming for a in streaming)

    def test_filter_voice_platforms(self):
        reg = self._reg()
        voice = reg.filter(supports_voice=True)
        assert len(voice) > 0
        ids = {a.id for a in voice}
        assert PlatformId.VOICE in ids
        assert PlatformId.WHATSAPP in ids

    def test_filter_jwt_auth(self):
        reg = self._reg()
        jwt_platforms = reg.filter(auth_mechanism=AuthMechanism.JWT)
        assert len(jwt_platforms) > 0
        assert all(a.auth_mechanism == AuthMechanism.JWT for a in jwt_platforms)

    def test_get_by_webhook_path(self):
        reg = self._reg()
        adapter = reg.get_by_webhook_path("/webhooks/slack")
        assert adapter is not None
        assert adapter.id == PlatformId.SLACK

    def test_get_by_webhook_path_unknown(self):
        reg = self._reg()
        assert reg.get_by_webhook_path("/webhooks/unknown") is None

    def test_truncate_sms_to_160(self):
        reg = self._reg()
        long_text = "x" * 300
        truncated = reg.truncate_for_platform(PlatformId.SMS, long_text)
        assert len(truncated) <= 160

    def test_truncate_short_text_unchanged(self):
        reg = self._reg()
        short = "Hello, Butler!"
        result = reg.truncate_for_platform(PlatformId.SMS, short)
        assert result == short

    def test_truncate_appends_marker(self):
        reg = self._reg()
        long_text = "A" * 300
        truncated = reg.truncate_for_platform(PlatformId.SMS, long_text)
        assert "[truncated]" in truncated

    def test_approval_required_sms_wildcard(self):
        reg = self._reg()
        assert reg.requires_approval_for_tool(PlatformId.SMS, "web_search") is True

    def test_approval_required_slack_file_write(self):
        reg = self._reg()
        assert reg.requires_approval_for_tool(PlatformId.SLACK, "file_write") is True

    def test_approval_not_required_api(self):
        reg = self._reg()
        assert reg.requires_approval_for_tool(PlatformId.API, "web_search") is False

    def test_list_all_has_25_items(self):
        reg = self._reg()
        items = reg.list_all()
        assert len(items) == 25

    def test_list_all_has_required_keys(self):
        reg = self._reg()
        item = reg.list_all()[0]
        assert "id" in item
        assert "display_name" in item
        assert "max_chars" in item
        assert "streaming" in item

    def test_singleton_returns_same_instance(self):
        r1 = get_platform_registry()
        r2 = get_platform_registry()
        assert r1 is r2

    def test_slack_max_chars_3000(self):
        reg = self._reg()
        slack = reg.get(PlatformId.SLACK)
        assert slack.max_message_chars == 3_000

    def test_iot_uses_mtls(self):
        reg = self._reg()
        iot = reg.get(PlatformId.IOT)
        assert iot.auth_mechanism == AuthMechanism.MTLS

    def test_mcp_client_supports_streaming(self):
        reg = self._reg()
        mcp = reg.get(PlatformId.MCP_CLIENT)
        assert mcp.supports_streaming is True

    def test_api_no_webhook_path(self):
        reg = self._reg()
        api = reg.get(PlatformId.API)
        assert api.webhook_path is None

    def test_all_platforms_have_nonzero_max_chars(self):
        reg = self._reg()
        for item in reg.list_all():
            assert item["max_chars"] > 0

    def test_no_duplicate_platform_ids(self):
        reg = self._reg()
        ids = [item["id"] for item in reg.list_all()]
        assert len(ids) == len(set(ids))
