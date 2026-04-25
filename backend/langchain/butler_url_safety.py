"""
URL safety checks — Butler-owned version.

Blocks requests to private/internal network addresses to prevent SSRF.
This is a Butler-owned version that removes Hermes CLI config dependencies.
"""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Hostnames that should always be blocked regardless of IP resolution
_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
    }
)

# IPs and networks that should always be blocked
_ALWAYS_BLOCKED_IPS = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure/DO/Oracle metadata
        ipaddress.ip_address("169.254.170.2"),  # AWS ECS task metadata
        ipaddress.ip_address("169.254.169.253"),  # Azure IMDS wire server
        ipaddress.ip_address("fd00:ec2::254"),  # AWS metadata (IPv6)
        ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud metadata
    }
)
_ALWAYS_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),  # Entire link-local range
)

# Trusted hostnames allowed to resolve to private IPs
_TRUSTED_PRIVATE_IP_HOSTS = frozenset(
    {
        "multimedia.nt.qq.com.cn",
    }
)

# CGNAT range not covered by ipaddress.is_private
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# Butler config toggle for allowing private URLs
_allow_private_resolved = False
_cached_allow_private: bool = False


def _global_allow_private_urls() -> bool:
    """Return True when Butler allows private-IP resolution.

    Checks Butler environment variables instead of Hermes config.
    """
    global _allow_private_resolved, _cached_allow_private
    if _allow_private_resolved:
        return _cached_allow_private

    _allow_private_resolved = True
    _cached_allow_private = False  # safe default

    # Butler env var override
    env_val = os.getenv("BUTLER_ALLOW_PRIVATE_URLS", "").strip().lower()
    if env_val in ("true", "1", "yes"):
        _cached_allow_private = True
        return _cached_allow_private
    if env_val in ("false", "0", "no"):
        return _cached_allow_private

    return _cached_allow_private


def _reset_allow_private_cache() -> None:
    """Reset the cached toggle — only for tests."""
    global _allow_private_resolved, _cached_allow_private
    _allow_private_resolved = False
    _cached_allow_private = False


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP should be blocked for SSRF protection."""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    return ip in _CGNAT_NETWORK


def _allows_private_ip_resolution(hostname: str, scheme: str) -> bool:
    """Return True when a trusted HTTPS hostname may bypass IP-class blocking."""
    return scheme == "https" and hostname in _TRUSTED_PRIVATE_IP_HOSTS


def is_safe_url(url: str) -> bool:
    """Return True if the URL target is not a private/internal address.

    Resolves the hostname to an IP and checks against private ranges.
    Fails closed: DNS errors and unexpected exceptions block the request.

    Cloud metadata endpoints remain blocked regardless of config.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        scheme = (parsed.scheme or "").strip().lower()
        if not hostname:
            return False

        # Block known internal hostnames — ALWAYS
        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning("Blocked request to internal hostname: %s", hostname)
            return False

        # Check the global toggle AFTER blocking metadata hostnames
        allow_all_private = _global_allow_private_urls()
        allow_private_ip = _allows_private_ip_resolution(hostname, scheme)

        # Try to resolve and check IP
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            logger.warning("Blocked request — DNS resolution failed for: %s", hostname)
            return False

        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            # Always block cloud metadata IPs and link-local
            if ip in _ALWAYS_BLOCKED_IPS or any(ip in net for net in _ALWAYS_BLOCKED_NETWORKS):
                logger.warning(
                    "Blocked request to cloud metadata address: %s -> %s",
                    hostname,
                    ip_str,
                )
                return False

            if not allow_all_private and not allow_private_ip and _is_blocked_ip(ip):
                logger.warning(
                    "Blocked request to private/internal address: %s -> %s",
                    hostname,
                    ip_str,
                )
                return False

        if allow_all_private:
            logger.debug(
                "Allowing private/internal resolution (BUTLER_ALLOW_PRIVATE_URLS=true): %s",
                hostname,
            )
        elif allow_private_ip:
            logger.debug(
                "Allowing trusted hostname despite private/internal resolution: %s",
                hostname,
            )

        return True

    except Exception as exc:
        logger.warning("Blocked request — URL safety check error for %s: %s", url, exc)
        return False
