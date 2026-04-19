"""Device policy and explicit trust gating.

Prevents commands from mutating devices that are offline, blocked, or missing
the correct pairing trust configurations.
"""

import structlog
from dataclasses import dataclass

from domain.device.models import DeviceRegistry

logger = structlog.get_logger(__name__)

@dataclass
class PolicyResult:
    allowed: bool
    reason: str | None = None

class DevicePolicy:
    """Evaluates physical command risks against device states."""
    
    @staticmethod
    def evaluate_dispatch(device: DeviceRegistry, requester_account_id: str) -> PolicyResult:
        # 1. Ownership & Tenancy Enforcements
        if str(device.owner_account_id) != requester_account_id:
            logger.warning("policy_denied_ownership", expected=str(device.owner_account_id), received=requester_account_id)
            return PolicyResult(allowed=False, reason="Account does not own this device surface.")
            
        # 2. Network verification
        if device.online_state == "offline":
            logger.info("policy_denied_offline", device=device.id)
            return PolicyResult(allowed=False, reason="Device is explicitly flagged as unreachable or offline natively.")
            
        # 3. Explicit Trust/Pairing Verification
        # 'pending' implies discovered but not validated.
        if device.trust_state != "trusted":
            logger.warning("policy_denied_trust", device=device.id, actual_trust=device.trust_state)
            return PolicyResult(allowed=False, reason=f"Device pairing state is '{device.trust_state}'. Explicit trust required.")
            
        return PolicyResult(allowed=True)
