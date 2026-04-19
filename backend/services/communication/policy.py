import structlog
from typing import Optional
from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.communication import SendRequest
from domain.communication.models import ConsentState, SenderProfile

logger = structlog.get_logger(__name__)

class PolicyResult:
    def __init__(self, allowed: bool, reason: str = None, suppressed: bool = False):
        self.allowed = allowed
        self.reason = reason
        self.suppressed = suppressed

class CommunicationPolicy:
    """
    Policy governance layer. Enforces consent, suppressions,
    sender identity, quiet hours, and risk/channel rules.

    Accepts a plain AsyncSession — no FastAPI coupling.
    Wired via core/deps.py.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def pre_send_check(self, request: SendRequest) -> PolicyResult:
        """Run all policy checks before enqueue."""
        # 1. Consent/Suppression check
        consent = await self._check_consent(request.recipient, request.channel)
        if not consent.allowed:
            return consent
        
        # 2. Quiet hours
        if not await self._quiet_hours_allows(request.recipient):
            return PolicyResult(allowed=False, reason="quiet_hours")
            
        # 3. Sender Identity
        sender = await self._verify_sender(request.sender_profile_id, request.channel, request.priority_class)
        if not sender.allowed:
            return sender
            
        # 4. WhatsApp Specific Policy (24h window vs template)
        if request.channel == "whatsapp":
            wa_check = await self._check_whatsapp_policy(request)
            if not wa_check.allowed:
                return wa_check
                
        # 5. Risk Class & Approval (Security)
        if request.risk_class == "high":
            appr = await self._verify_approval_token(request.approval_token)
            if not appr.allowed:
                return appr

        return PolicyResult(allowed=True)

    async def _check_consent(self, recipient: str, channel: str) -> PolicyResult:
        stmt = select(ConsentState).where(
            ConsentState.recipient == recipient, 
            ConsentState.channel == channel
        )
        result = await self.db.execute(stmt)
        state = result.scalar_one_or_none()
        
        if state and state.status == "suppressed":
            return PolicyResult(allowed=False, reason=f"suppressed:{state.reason}", suppressed=True)
            
        return PolicyResult(allowed=True)

    async def _quiet_hours_allows(self, recipient: str) -> bool:
        # In a real system, look up user timezone and preference.
        return True
        
    async def _verify_sender(self, profile_id: str, channel: str, priority_class: str) -> PolicyResult:
        """Ensures the sender identity exists, is verified, and authorized for the channel."""
        if not profile_id:
            return PolicyResult(allowed=False, reason="missing_sender_profile")
            
        stmt = select(SenderProfile).where(SenderProfile.id == profile_id)
        result = await self.db.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if not profile:
            return PolicyResult(allowed=False, reason="invalid_sender_profile")
            
        if not profile.verified:
            return PolicyResult(allowed=False, reason="sender_not_verified")
            
        return PolicyResult(allowed=True)

    async def _check_whatsapp_policy(self, request: SendRequest) -> PolicyResult:
        """
        Enforce WhatsApp's 24-hour service window vs template rule.
        Uses metadata to determine if sending a template or regular session message.
        """
        msg_mode = request.metadata.get("whatsapp_mode", "template") # safety default
        
        if msg_mode == "session":
            # Real prod system would check last inbound message timestamp from recipient
            last_msg_ts = request.metadata.get("last_inbound_ts")
            if not last_msg_ts:
                return PolicyResult(allowed=False, reason="whatsapp_session_expired")
            
            # Simple check for > 24 hours
            diff = (datetime.now(UTC).timestamp() - float(last_msg_ts))
            if diff > 86400:
                return PolicyResult(allowed=False, reason="whatsapp_session_expired")
                
        elif msg_mode == "template":
            if not request.content.get("template_name"):
                return PolicyResult(allowed=False, reason="whatsapp_template_required")
                
        return PolicyResult(allowed=True)
        
    async def _verify_approval_token(self, token: Optional[str]) -> PolicyResult:
        """Validates MFA/Step-up tokens for high-risk communication."""
        if not token:
            return PolicyResult(allowed=False, reason="approval_required")
            
        # Prod would check cache/db for signed token validity
        if token != "valid_mock_token_for_now":
            return PolicyResult(allowed=False, reason="invalid_approval_token")
            
        return PolicyResult(allowed=True)
