"""Voice/Telephony Providers — VoiceCall, Twilio, Vonage."""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)


# ── Twilio Provider ─────────────────────────────────────────────────────────


class TwilioVoiceProvider:
    """Twilio Voice/Telephony Provider."""

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
        tenant_id: str | None = None,
    ):
        self._account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
        self._auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
        self._from_number = from_number or os.environ.get("TWILIO_FROM_NUMBER")
        self.tenant_id = tenant_id or "default"
        if self._account_sid and self._auth_token:
            self._client = httpx.AsyncClient(
                auth=(self._account_sid, self._auth_token),
                timeout=_DEFAULT_TIMEOUT,
            )
        else:
            self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def make_call(self, to: str, twiml_url: str) -> dict[str, Any]:
        """Make an outbound voice call."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls.json"
        payload = {
            "To": to,
            "From": self._from_number,
            "Url": twiml_url,
            "Method": "GET",
        }
        if self._safe_client and self.tenant_id and self._account_sid and self._auth_token:
            import base64

            auth_str = base64.b64encode(f"{self._account_sid}:{self._auth_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                data=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, data=payload)
        return response.json()

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        payload = {
            "To": to,
            "From": self._from_number,
            "Body": body,
        }
        if self._safe_client and self.tenant_id and self._account_sid and self._auth_token:
            import base64

            auth_str = base64.b64encode(f"{self._account_sid}:{self._auth_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                data=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, data=payload)
        return response.json()


# ── Vonage Provider ─────────────────────────────────────────────────────


class VonageVoiceProvider:
    """Vonage (Nexmo) Voice/Telephony Provider."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        application_id: str | None = None,
        from_number: str | None = None,
        tenant_id: str | None = None,
    ):
        self._api_key = api_key or os.environ.get("VONAGE_API_KEY")
        self._api_secret = api_secret or os.environ.get("VONAGE_API_SECRET")
        self._application_id = application_id or os.environ.get("VONAGE_APPLICATION_ID")
        self._from_number = from_number or os.environ.get("VONAGE_FROM_NUMBER")
        self.tenant_id = tenant_id or "default"
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def make_call(self, to: str, ncco_url: str) -> dict[str, Any]:
        """Make an outbound voice call."""
        url = "https://api.nexmo.com/v1/calls"
        payload = {
            "to": [{"type": "phone", "number": to}],
            "from": {"type": "phone", "number": self._from_number},
            "answer_url": [ncco_url],
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}:{self._api_secret}",
                    "Content-Type": "application/json",
                },
            )
        else:
            response = await self._client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}:{self._api_secret}",
                    "Content-Type": "application/json",
                },
            )
        return response.json()

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        url = "https://rest.nexmo.com/sms/json"
        payload = {
            "api_key": self._api_key,
            "api_secret": self._api_secret,
            "from": self._from_number,
            "to": to,
            "text": body,
        }
        if self._safe_client and self.tenant_id:
            response = await self._safe_client.post(url, self.tenant_id, data=payload)
        else:
            response = await self._client.post(url, data=payload)
        return response.json()


# ── Plivo Provider ───────────────────────────────────────────────────────


class PlivoVoiceProvider:
    """Plivo Voice/Telephony Provider."""

    def __init__(
        self,
        auth_id: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
        tenant_id: str | None = None,
    ):
        self._auth_id = auth_id or os.environ.get("PLIVO_AUTH_ID")
        self._auth_token = auth_token or os.environ.get("PLIVO_AUTH_TOKEN")
        self._from_number = from_number or os.environ.get("PLIVO_FROM_NUMBER")
        self.tenant_id = tenant_id or "default"
        if self._auth_id and self._auth_token:
            self._client = httpx.AsyncClient(
                auth=(self._auth_id, self._auth_token),
                timeout=_DEFAULT_TIMEOUT,
            )
        else:
            self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def make_call(self, to: str, answer_url: str) -> dict[str, Any]:
        """Make an outbound voice call."""
        url = f"https://api.plivo.com/v1/Account/{self._auth_id}/Call/"
        payload = {
            "from": self._from_number,
            "to": to,
            "answer_url": answer_url,
            "ring_timeout": 30,
        }
        if self._safe_client and self.tenant_id and self._auth_id and self._auth_token:
            import base64

            auth_str = base64.b64encode(f"{self._auth_id}:{self._auth_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, json=payload)
        return response.json()

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        url = f"https://api.plivo.com/v1/Account/{self._auth_id}/Message/"
        payload = {
            "src": self._from_number,
            "dst": to,
            "text": body,
        }
        if self._safe_client and self.tenant_id and self._auth_id and self._auth_token:
            import base64

            auth_str = base64.b64encode(f"{self._auth_id}:{self._auth_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                json=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, json=payload)
        return response.json()


# ── SignalWire Provider ────────────────────────────────────────────────


class SignalWireVoiceProvider:
    """SignalWire Voice/Telephony Provider."""

    def __init__(
        self,
        project_id: str | None = None,
        api_token: str | None = None,
        space_url: str | None = None,
        from_number: str | None = None,
        tenant_id: str | None = None,
    ):
        self._project_id = project_id or os.environ.get("SIGNALWIRE_PROJECT_ID")
        self._api_token = api_token or os.environ.get("SIGNALWIRE_API_TOKEN")
        self._space_url = space_url or os.environ.get("SIGNALWIRE_SPACE_URL")
        self._from_number = from_number or os.environ.get("SIGNALWIRE_FROM_NUMBER")
        self.tenant_id = tenant_id or "default"
        if self._project_id and self._api_token:
            self._client = httpx.AsyncClient(
                auth=(self._project_id, self._api_token),
                timeout=_DEFAULT_TIMEOUT,
            )
        else:
            self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        self._safe_client = SafeRequestClient(timeout=_DEFAULT_TIMEOUT)

    async def make_call(self, to: str, twiml_url: str) -> dict[str, Any]:
        """Make an outbound voice call."""
        url = f"{self._space_url}/api/laml/2010-04-01/Accounts/{self._project_id}/Calls.json"
        payload = {
            "From": self._from_number,
            "To": to,
            "Url": twiml_url,
        }
        if self._safe_client and self.tenant_id and self._project_id and self._api_token:
            import base64

            auth_str = base64.b64encode(f"{self._project_id}:{self._api_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                data=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, data=payload)
        return response.json()

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        """Send an SMS message."""
        url = f"{self._space_url}/api/laml/2010-04-01/Accounts/{self._project_id}/Messages.json"
        payload = {
            "From": self._from_number,
            "To": to,
            "Body": body,
        }
        if self._safe_client and self.tenant_id and self._project_id and self._api_token:
            import base64

            auth_str = base64.b64encode(f"{self._project_id}:{self._api_token}".encode()).decode()
            response = await self._safe_client.post(
                url,
                self.tenant_id,
                data=payload,
                headers={"Authorization": f"Basic {auth_str}"},
            )
        else:
            response = await self._client.post(url, data=payload)
        return response.json()


# ── Voice Factory ───────────────────────────────────────────────────────


class VoiceProviderFactory:
    """Factory for voice/telephony providers."""

    _instances = {}

    @classmethod
    def get_provider(cls, provider_type: str):
        """Return a voice provider instance."""
        if provider_type in cls._instances:
            return cls._instances[provider_type]

        provider = None
        if provider_type == "twilio":
            from services.ml.providers.voice import TwilioVoiceProvider

            provider = TwilioVoiceProvider()
        elif provider_type == "vonage":
            from services.ml.providers.voice import VonageVoiceProvider

            provider = VonageVoiceProvider()
        elif provider_type == "plivo":
            from services.ml.providers.voice import PlivoVoiceProvider

            provider = PlivoVoiceProvider()
        elif provider_type == "signalwire":
            from services.ml.providers.voice import SignalWireVoiceProvider

            provider = SignalWireVoiceProvider()
        else:
            raise ValueError(f"Unsupported voice provider: {provider_type}")

        cls._instances[provider_type] = provider
        return provider
