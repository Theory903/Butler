"""
SSRF Protection Service - Prevent Server-Side Request Forgery

Blocks requests to:
- Private IP ranges (RFC 1918, RFC 4193, link-local)
- Cloud metadata IPs (AWS, GCP, Azure)
- Localhost and loopback addresses
- Internal DNS names
"""

from __future__ import annotations

import ipaddress

import structlog

logger = structlog.get_logger(__name__)


# Blocked IP ranges
BLOCKED_IP_RANGES = [
    # RFC 1918 - Private IPv4
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # RFC 4193 - Private IPv6
    ipaddress.ip_network("fc00::/7"),
    # Link-local IPv4
    ipaddress.ip_network("169.254.0.0/16"),
    # Link-local IPv6
    ipaddress.ip_network("fe80::/10"),
    # Loopback IPv4
    ipaddress.ip_network("127.0.0.0/8"),
    # Loopback IPv6
    ipaddress.ip_network("::1/128"),
    # Cloud metadata IPs
    ipaddress.ip_network("169.254.169.254/32"),  # AWS
    ipaddress.ip_network("metadata.google.internal"),  # GCP
    ipaddress.ip_network("169.254.169.254"),  # Azure
]

# Blocked domains (internal DNS names)
BLOCKED_DOMAINS = [
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
]


class SSRFProtectionError(Exception):
    """Raised when SSRF attempt is detected."""

    def __init__(self, reason: str, target: str) -> None:
        self.reason = reason
        self.target = target
        super().__init__(f"SSRF blocked: {reason} - {target}")


class SSRFProtectionService:
    """SSRF protection service."""

    def __init__(self, allowlist: list[str] | None = None) -> None:
        """
        Initialize SSRF protection service.

        Args:
            allowlist: List of allowed domains/IPs (overrides blocklist)
        """
        self._allowlist = set(allowlist) if allowlist else set()

    def is_allowed(self, target: str) -> bool:
        """
        Check if a target is allowed (not blocked by SSRF protection).

        Args:
            target: URL or hostname/IP to check

        Returns:
            True if allowed, False if blocked

        Raises:
            SSRFProtectionError: If target is blocked
        """
        # Check allowlist first
        if target in self._allowlist:
            return True

        # Check blocked domains
        for blocked_domain in BLOCKED_DOMAINS:
            if blocked_domain in target.lower():
                logger.warning(
                    "ssrf_blocked_domain",
                    target=target,
                    blocked_domain=blocked_domain,
                )
                raise SSRFProtectionError("blocked domain", target)

        # Check if target is an IP address
        try:
            ip = ipaddress.ip_address(target)
            for blocked_range in BLOCKED_IP_RANGES:
                if ip in blocked_range:
                    logger.warning(
                        "ssrf_blocked_ip",
                        target=target,
                        blocked_range=str(blocked_range),
                    )
                    raise SSRFProtectionError("blocked IP range", target)
        except ValueError:
            # Not an IP address, could be a hostname
            pass

        return True

    def validate_url(self, url: str) -> bool:
        """
        Validate a URL for SSRF safety.

        Args:
            url: Full URL to validate

        Returns:
            True if safe

        Raises:
            SSRFProtectionError: If URL is blocked
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Check hostname
        if parsed.hostname:
            self.is_allowed(parsed.hostname)

        return True

    def add_to_allowlist(self, target: str) -> None:
        """
        Add a target to the allowlist.

        Args:
            target: Domain or IP to allow
        """
        self._allowlist.add(target)
        logger.info("ssrf_allowlist_added", target=target)

    def remove_from_allowlist(self, target: str) -> None:
        """
        Remove a target from the allowlist.

        Args:
            target: Domain or IP to remove
        """
        self._allowlist.discard(target)
        logger.info("ssrf_allowlist_removed", target=target)


# Singleton instance
_ssrf_service: SSRFProtectionService | None = None


def get_ssrf_protection_service() -> SSRFProtectionService:
    """Get the singleton SSRF protection service."""
    global _ssrf_service
    if _ssrf_service is None:
        _ssrf_service = SSRFProtectionService()
    return _ssrf_service
