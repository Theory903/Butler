import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import Request

from api.schemas.communication import AuthenticityResult, CanonicalInbound

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

logger = structlog.get_logger(__name__)


class WebhookValidator:
    """
    Secure inbound webhook validator enforcing strict cryptographic checks.
    Never falls back to "accept all".
    """

    def __init__(self):
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.whatsapp_secret = os.getenv("WHATSAPP_APP_SECRET", "").encode("utf-8")
        self.sendgrid_pk_hex = os.getenv("SENDGRID_WEBHOOK_PUBLIC_KEY", "")

    async def verify_twilio(self, request: Request) -> bool:
        """Twilio strict URL+FormData HMAC-SHA1 validation."""
        signature = request.headers.get("x-twilio-signature")
        if not signature or not self.twilio_auth_token:
            return False

        url = str(request.url)
        form_data = await request.form()

        # Twilio sorts form params by key, concats key+value, appends to URL
        data_to_sign = url
        for k in sorted(form_data.keys()):
            data_to_sign += f"{k}{form_data[k]}"

        expected_sig = base64.b64encode(
            hmac.new(
                self.twilio_auth_token.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1
            ).digest()
        ).decode("utf-8")

        return hmac.compare_digest(expected_sig, signature)

    async def verify_whatsapp(self, request: Request, body: bytes) -> bool:
        """Meta Webhooks strict SHA256 HMAC payload validation."""
        signature_header = request.headers.get("x-hub-signature-256")
        if (
            not signature_header
            or not signature_header.startswith("sha256=")
            or not self.whatsapp_secret
        ):
            return False

        signature = signature_header.split("sha256=")[-1]
        expected_sig = hmac.new(self.whatsapp_secret, body, hashlib.sha256).hexdigest()

        return hmac.compare_digest(expected_sig, signature)

    async def verify_sendgrid(self, request: Request, body: bytes) -> bool:
        """SendGrid Event Webhook strict Ed25519 public key validation."""
        if not HAS_CRYPTOGRAPHY:
            logger.error(
                "Rejecting SendGrid webhook: cryptography package missing. Cannot verify signature safely."
            )
            return False

        signature = request.headers.get("x-twilio-email-event-webhook-signature")
        timestamp = request.headers.get("x-twilio-email-event-webhook-timestamp")

        if not signature or not timestamp or not self.sendgrid_pk_hex:
            return False

        try:
            public_key_bytes = base64.b64decode(self.sendgrid_pk_hex)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

            payload_to_verify = timestamp.encode("utf-8") + body
            signature_bytes = base64.b64decode(signature)

            public_key.verify(signature_bytes, payload_to_verify)
            return True
        except Exception as e:
            logger.warning(f"SendGrid signature verification failed: {str(e)}")
            return False


class InboundNormalizer:
    """Standardizes disparate provider webhooks into Butler CanonicalInbound envelopes."""

    async def normalize(self, provider: str, payload: dict[str, Any]) -> CanonicalInbound | None:
        if provider == "twilio":
            return self._normalize_sms(payload)
        return None

    def _normalize_sms(self, payload: dict[str, Any]) -> CanonicalInbound:
        return CanonicalInbound(
            channel="sms",
            provider="twilio",
            provider_message_id=payload.get("MessageSid", ""),
            external_sender=payload.get("From", ""),
            recipient_identity=payload.get("To", ""),
            received_at=datetime.now(UTC),  # Twilio doesn't always send TS in form
            content={"text": payload.get("Body", "")},
            attachments=[],
            authenticity=AuthenticityResult(verified=True, method="twilio_signature", details={}),
        )
