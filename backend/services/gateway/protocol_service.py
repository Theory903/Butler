import time
import uuid
from typing import Any

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from api.schemas.mercury import ConnectParams, MercuryEvent, MercuryRequest, MercuryResponse
from services.auth.jwt import get_jwks_manager

logger = structlog.get_logger(__name__)


class MercuryProtocolService:
    """Mercury Gateway Protocol implementation (v3).

    Handles the high-assurance handshake, frame routing, and node/operator
    lifecycle management as defined in OpenClaw.
    """

    def __init__(self):
        self.sessions: dict[str, dict[str, Any]] = {}
        self.challenges: dict[str, dict[str, Any]] = {}

    def create_challenge(self) -> MercuryEvent:
        """Create a connect.challenge event frame."""
        nonce = str(uuid.uuid4())
        ts = int(time.time() * 1000)
        self.challenges[nonce] = {"ts": ts}

        return MercuryEvent(event="connect.challenge", payload={"nonce": nonce, "ts": ts})

    async def handle_connect(self, req: MercuryRequest) -> MercuryResponse:
        """Process a 'connect' request frame."""
        try:
            params = ConnectParams(**req.params)

            # 1. Protocol Version Check
            if params.minProtocol > 3 or params.maxProtocol < 3:
                return self._error(req.id, "PROTOCOL_MISMATCH", "Server supports Mercury v3 only")

            # 2. Challenge Verification (if device auth is mandatory)
            device = params.device
            nonce = device.get("nonce")
            if not nonce or nonce not in self.challenges:
                return self._error(
                    req.id, "DEVICE_AUTH_NONCE_REQUIRED", "Challenge nonce missing or invalid"
                )

            # Verify Signature (ED25519)
            if not self._verify_device_signature(device):
                return self._error(
                    req.id, "DEVICE_AUTH_SIGNATURE_INVALID", "Device signature check failed"
                )

            # 3. Auth Token Verification (JWT RS256)
            token = params.auth.get("token")
            if not token:
                return self._error(req.id, "AUTH_REQUIRED", "Authentication token missing")

            # Validate JWT against JWKS manager
            try:
                jwks = get_jwks_manager()
                claims = jwks.verify_token(token)
                logger.info("jwt_validated", device_id=device.get("id"), sub=claims.get("sub"))
            except Exception as e:
                logger.warning("jwt_validation_failed", error=str(e), device_id=device.get("id"))
                return self._error(req.id, "AUTH_INVALID", f"Invalid token: {str(e)}")

            # 4. Negotiate Role/Scopes
            role = params.role
            scopes = params.scopes if role == "operator" else []

            conn_id = str(uuid.uuid4())
            self.sessions[conn_id] = {
                "role": role,
                "scopes": scopes,
                "caps": params.caps,
                "client": params.client,
                "device_id": device.get("id"),
            }

            return MercuryResponse(
                id=req.id,
                ok=True,
                payload={
                    "type": "hello-ok",
                    "protocol": 3,
                    "server": {"version": "1.0.0", "connId": conn_id},
                    "features": {
                        "methods": ["health", "status", "node.pair.*", "skills.search"],
                        "events": ["presence", "tick", "health"],
                    },
                    "auth": {"role": role, "scopes": scopes},
                    "policy": {
                        "maxPayload": 26214400,
                        "maxBufferedBytes": 52428800,
                        "tickIntervalMs": 15000,
                    },
                },
            )

        except Exception as e:
            logger.exception("mercury_connect_error")
            return self._error(req.id, "INTERNAL_ERROR", str(e))

    def _verify_device_signature(self, device: dict[str, Any]) -> bool:
        """Verify the ED25519 signature of the connect challenge."""
        public_key_hex = device.get("publicKey")
        signature_hex = device.get("signature")
        nonce = device.get("nonce")
        signed_at = device.get("signedAt")

        if not all([public_key_hex, signature_hex, nonce, signed_at]):
            return False

        try:
            # Reconstruct the signed payload (OpenClaw v3 format)
            # In v3, we sign: nonce + signed_at + device_id
            payload = f"{nonce}:{signed_at}:{device.get('id')}".encode()

            public_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            public_key.verify(bytes.fromhex(signature_hex), payload)
            return True
        except (InvalidSignature, ValueError, Exception):
            return False

    def _error(self, req_id: str, code: str, message: str) -> MercuryResponse:
        return MercuryResponse(id=req_id, ok=False, error={"code": code, "message": message})
