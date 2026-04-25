import pytest

from domain.policy.capability_flags import CapabilityArea, TrustLevel
from domain.policy.industry_profiles import IndustryProfile, check_profile_capability
from domain.policy.product_tiers import ProductTier, check_capability


class TestCapabilityEnforcement:
    @pytest.mark.parametrize(
        ("tier", "area", "allowed"),
        [
            (ProductTier.PERSONAL, CapabilityArea.WEB_SEARCH, True),
            (ProductTier.PERSONAL, CapabilityArea.FINANCE_GATEWAY, False),
            (ProductTier.PRO, CapabilityArea.DATA_ANALYSIS, True),
            (ProductTier.PRO, CapabilityArea.FINANCE_GATEWAY, False),
        ],
    )
    def test_tier_capabilities(self, tier, area, allowed):
        res = check_capability(tier, area)
        assert res.allowed is allowed
        assert isinstance(res.reason, str)

    def test_enterprise_unlocks_all_base_tier_capabilities(self):
        for area in CapabilityArea:
            res = check_capability(ProductTier.ENTERPRISE, area)
            assert res.allowed is True

    def test_industry_profile_can_override_tier_allow(self):
        res = check_profile_capability(
            ProductTier.ENTERPRISE,
            IndustryProfile.HEALTHCARE,
            CapabilityArea.WEB_SEARCH,
        )
        assert res.allowed is False
        assert "restricted by the 'healthcare' industry profile" in res.reason

    def test_healthcare_profile_allows_health_integration(self):
        res = check_profile_capability(
            ProductTier.ENTERPRISE,
            IndustryProfile.HEALTHCARE,
            CapabilityArea.HEALTH_INTEGRATION,
        )
        assert res.allowed is True

    def test_trust_level_ordering(self):
        # Numeric priority: Lower is higher trust (0=INTERNAL, 3=UNTRUSTED)
        assert TrustLevel.INTERNAL < TrustLevel.VERIFIED_USER
        assert TrustLevel.VERIFIED_USER < TrustLevel.PEER_AGENT
        assert TrustLevel.PEER_AGENT < TrustLevel.UNTRUSTED
