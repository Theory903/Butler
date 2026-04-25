"""
Circuit breakers and retry policies by RiskTier.
"""

from enum import Enum

from tenacity import stop_after_attempt, wait_exponential


class RiskTier(Enum):
    TIER_0_BUILTIN = 0
    TIER_1_READ = 1
    TIER_2_WRITE = 2
    TIER_3_DEVICE = 3
    TIER_4_APPROVAL = 4


RETRY_POLICIES = {
    RiskTier.TIER_0_BUILTIN: {"stop": stop_after_attempt(1)},
    RiskTier.TIER_1_READ: {
        "stop": stop_after_attempt(2),
        "wait": wait_exponential(multiplier=1, min=1, max=10),
    },
    RiskTier.TIER_2_WRITE: {
        "stop": stop_after_attempt(3),
        "wait": wait_exponential(multiplier=1, min=1, max=10),
    },
    RiskTier.TIER_3_DEVICE: {"stop": stop_after_attempt(1)},
    RiskTier.TIER_4_APPROVAL: {"stop": stop_after_attempt(1)},
}


def get_retry_policy(risk_tier: int):
    """Get retry policy for given risk tier."""
    tier = (
        RiskTier(risk_tier) if risk_tier in [e.value for e in RiskTier] else RiskTier.TIER_0_BUILTIN
    )
    return RETRY_POLICIES[tier]
