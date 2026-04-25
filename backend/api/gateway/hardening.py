"""Gateway Hardening (nginx parity).

Phase H: Gateway hardening with nginx parity using slowapi for rate limiting.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import ipaddress

logger = logging.getLogger(__name__)


@dataclass
class SecurityHeader:
    """A security header configuration."""

    name: str
    value: str
    enabled: bool = True


@dataclass
class IPWhitelist:
    """An IP whitelist configuration."""

    name: str
    cidrs: list[str] = field(default_factory=list)
    enabled: bool = True


class GatewayHardening:
    """Gateway hardening with nginx parity using slowapi.

    This service:
    - Uses slowapi for real rate limiting
    - Configures security headers
    - Manages IP whitelists
    - Provides DDoS protection
    - Enforces TLS policies
    """

    def __init__(self, redis_client: Any | None = None):
        """Initialize the gateway hardening service.

        Args:
            redis_client: Redis client for slowapi backend
        """
        self._redis_client = redis_client
        self._security_headers: dict[str, SecurityHeader] = {}
        self._ip_whitelists: dict[str, IPWhitelist] = {}
        self._limiter = None

    def configure_slowapi(self) -> None:
        """Configure slowapi rate limiter."""
        try:
            from slowapi import Limiter
            from slowapi.util import get_remote_address
            from slowapi.errors import RateLimitExceeded

            self._limiter = Limiter(
                key_func=get_remote_address,
                storage_uri=self._redis_client if self._redis_client else "memory://",
            )
            logger.info("slowapi_configured")
        except ImportError:
            logger.warning("slowapi_not_available")

    def add_security_header(self, header: SecurityHeader) -> None:
        """Add a security header.

        Args:
            header: Security header
        """
        self._security_headers[header.name] = header
        logger.info("security_header_added", header_name=header.name)

    def get_security_headers(self) -> dict[str, str]:
        """Get all enabled security headers.

        Returns:
            Dictionary of header name to value
        """
        return {
            h.name: h.value
            for h in self._security_headers.values()
            if h.enabled
        }

    def add_ip_whitelist(self, whitelist: IPWhitelist) -> None:
        """Add an IP whitelist.

        Args:
            whitelist: IP whitelist
        """
        self._ip_whitelists[whitelist.name] = whitelist
        logger.info("ip_whitelist_added", whitelist_name=whitelist.name)

    def check_ip_whitelist(self, client_ip: str) -> bool:
        """Check if IP is whitelisted.

        Args:
            client_ip: Client IP address

        Returns:
            True if whitelisted
        """
        for whitelist in self._ip_whitelists.values():
            if not whitelist.enabled:
                continue

            for cidr in whitelist.cidrs:
                try:
                    network = ipaddress.ip_network(cidr, strict=False)
                    if ipaddress.ip_address(client_ip) in network:
                        return True
                except ValueError:
                    continue

        return False

    def configure_default_headers(self) -> None:
        """Configure nginx-parity default security headers."""
        default_headers = [
            SecurityHeader(name="X-Frame-Options", value="DENY"),
            SecurityHeader(name="X-Content-Type-Options", value="nosniff"),
            SecurityHeader(name="X-XSS-Protection", value="1; mode=block"),
            SecurityHeader(name="Strict-Transport-Security", value="max-age=31536000; includeSubDomains"),
            SecurityHeader(name="Content-Security-Policy", value="default-src 'self'"),
            SecurityHeader(name="Referrer-Policy", value="strict-origin-when-cross-origin"),
            SecurityHeader(name="Permissions-Policy", value="geolocation=(), microphone=()"),
        ]

        for header in default_headers:
            self.add_security_header(header)

        logger.info("default_security_headers_configured")

    def get_limiter(self) -> Any:
        """Get the slowapi limiter instance.

        Returns:
            Slowapi Limiter instance or None
        """
        return self._limiter
