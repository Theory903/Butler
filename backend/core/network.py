"""Network utilities — Phase 8b.

Includes SSRF (Server-Side Request Forgery) protection for outgoing 
webhook deliveries, as found in OpenClaw's Oracle-Grade implementation.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Reserved / Private IP ranges to block for SSRF protection
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
]


def is_safe_url(url: str) -> bool:
    """Check if a URL is safe from SSRF by validating the resolved IP."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        host = parsed.hostname
        if not host:
            return False
        
        # Resolve hostname to IP
        # NOTE: In production, this should ideally be handled at the transport layer
        # to prevent DNS rebinding attacks. This is a baseline check.
        ip_address = socket.gethostbyname(host)
        ip = ipaddress.ip_address(ip_address)
        
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                logger.warning("ssrf_blocked_request", url=url, ip=ip_address)
                return False
        
        return True
    except (ValueError, socket.gaierror):
        return False


async def safe_request(
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with SSRF protection."""
    if not is_safe_url(url):
        raise ValueError(f"SSRF Protection: Blocked request to {url}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.request(method, url, **kwargs)
