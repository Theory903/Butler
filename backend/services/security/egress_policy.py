"""
EgressPolicy - Network Egress Control

Production-grade network egress policy for SSRF prevention.
Controls which external endpoints tools can access.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import StrEnum

import structlog

logger = structlog.get_logger(__name__)


class EgressDecision(StrEnum):
    """Egress policy decision."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class EgressRule:
    """Egress rule definition."""

    pattern: str
    decision: EgressDecision
    description: str


class EgressPolicy:
    """
    Network egress policy for SSRF prevention.

    All outbound HTTP requests from tools must go through this policy.
    Blocks private/reserved IP ranges and allows only configured domains.
    """

    # Private IP ranges to block
    PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    # Metadata endpoints to block
    METADATA_ENDPOINTS = [
        "metadata.google.internal",
        "169.254.169.254",
        "metadata.aws.amazon.com",
    ]

    def __init__(
        self,
        *,
        allowlist: list[str] | None = None,
        blocklist: list[str] | None = None,
    ) -> None:
        """
        Initialize egress policy.

        Args:
            allowlist: List of allowed domain patterns (e.g., "*.example.com")
            blocklist: List of blocked domain patterns
        """
        self._allowlist = allowlist or []
        self._blocklist = blocklist or []

    def check_url(self, url: str, tenant_id: str) -> tuple[EgressDecision, str]:
        """
        Check if URL is allowed by egress policy.

        Args:
            url: URL to check
            tenant_id: Tenant UUID for logging

        Returns:
            Tuple of (decision, reason)
        """
        # Parse URL
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
        except Exception as e:
            return EgressDecision.DENY, f"Invalid URL: {e}"

        # Only allow http and https
        if parsed.scheme not in ("http", "https"):
            return EgressDecision.DENY, f"Protocol not allowed: {parsed.scheme}"

        # Block metadata endpoints
        hostname = parsed.hostname or ""
        if any(metadata in hostname for metadata in self.METADATA_ENDPOINTS):
            logger.warning(
                "egress_denied_metadata_endpoint",
                tenant_id=tenant_id,
                url=url,
                hostname=hostname,
            )
            return EgressDecision.DENY, "Metadata endpoint blocked"

        # Check blocklist
        if self._matches_pattern(hostname, self._blocklist):
            logger.warning(
                "egress_denied_blocklist",
                tenant_id=tenant_id,
                url=url,
                hostname=hostname,
            )
            return EgressDecision.DENY, "Domain in blocklist"

        # Check allowlist (if configured)
        if self._allowlist and not self._matches_pattern(hostname, self._allowlist):
            logger.warning(
                "egress_denied_not_in_allowlist",
                tenant_id=tenant_id,
                url=url,
                hostname=hostname,
            )
            return EgressDecision.DENY, "Domain not in allowlist"

        # Resolve hostname and check IP ranges
        try:
            import socket

            ip_addresses = socket.getaddrinfo(hostname, None)
            for addr_info in ip_addresses:
                ip_str = addr_info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if self._is_private_ip(ip):
                        logger.warning(
                            "egress_denied_private_ip",
                            tenant_id=tenant_id,
                            url=url,
                            ip=ip_str,
                        )
                        return EgressDecision.DENY, f"Private IP blocked: {ip_str}"
                except ValueError:
                    continue
        except Exception as e:
            logger.warning(
                "egress_dns_resolution_failed",
                tenant_id=tenant_id,
                url=url,
                error=str(e),
            )
            return EgressDecision.DENY, f"DNS resolution failed: {e}"

        logger.info(
            "egress_allowed",
            tenant_id=tenant_id,
            url=url,
        )
        return EgressDecision.ALLOW, "Allowed"

    def _matches_pattern(self, hostname: str, patterns: list[str]) -> bool:
        """Check if hostname matches any pattern."""
        return any(self._wildcard_match(hostname, pattern) for pattern in patterns)

    def _wildcard_match(self, hostname: str, pattern: str) -> bool:
        """Simple wildcard matching for domain patterns."""
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            domain = pattern[2:]
            return hostname == domain or hostname.endswith(f".{domain}")
        return hostname == pattern

    def _is_private_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP is in private range."""
        return any(ip in private_range for private_range in self.PRIVATE_RANGES)

    @classmethod
    def get_default(cls) -> EgressPolicy:
        """Get default egress policy with sensible defaults."""
        return cls(
            allowlist=None,  # Allow all by default (can be restricted per tenant)
            blocklist=[
                "*.internal",
                "*.local",
                "*.lan",
            ],
        )
