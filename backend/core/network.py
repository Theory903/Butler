from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

_ALLOWED_SCHEMES: Final[set[str]] = {"http", "https"}
_DEFAULT_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(10.0, connect=5.0)
_MAX_REDIRECTS: Final[int] = 3

_BLOCKED_HOSTNAMES: Final[set[str]] = {
    "localhost",
    "localhost.localdomain",
}

_BLOCKED_NETWORKS: Final[tuple[ipaddress._BaseNetwork, ...]] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("::/128"),
)

_ALLOWED_PORTS: Final[set[int]] = {80, 443}


class SSRFProtectionError(ValueError):
    """Raised when an outbound request is blocked by SSRF protection."""


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    family: int
    ip: str


def _is_blocked_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)

    if (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        return True

    return any(ip_obj in network for network in _BLOCKED_NETWORKS)


def _normalize_hostname(hostname: str | None) -> str:
    if not hostname:
        raise SSRFProtectionError("URL must include a hostname")
    return hostname.strip().lower().rstrip(".")


def _validate_url_shape(url: str) -> tuple[str, int]:
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFProtectionError(f"Invalid URL: {url}") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFProtectionError(f"Blocked scheme: {parsed.scheme!r}")

    if parsed.username or parsed.password:
        raise SSRFProtectionError("Userinfo in URL is not allowed")

    hostname = _normalize_hostname(parsed.hostname)

    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        raise SSRFProtectionError(f"Blocked hostname: {hostname}")

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    if port not in _ALLOWED_PORTS:
        raise SSRFProtectionError(f"Blocked port: {port}")

    return hostname, port


def resolve_and_validate_host(url: str) -> list[ResolvedAddress]:
    """Resolve all host addresses and reject blocked targets."""
    hostname, port = _validate_url_shape(url)

    try:
        infos = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise SSRFProtectionError(f"DNS resolution failed for host: {hostname}") from exc

    resolved: list[ResolvedAddress] = []
    seen: set[str] = set()

    for family, _socktype, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)

        if _is_blocked_ip(ip_str):
            logger.warning(
                "ssrf_blocked_resolution",
                url=url,
                hostname=hostname,
                ip=ip_str,
            )
            raise SSRFProtectionError(f"Blocked resolved IP: {ip_str}")

        resolved.append(ResolvedAddress(family=family, ip=ip_str))

    if not resolved:
        raise SSRFProtectionError(f"No valid resolved addresses for host: {hostname}")

    return resolved


def is_safe_url(url: str) -> bool:
    """Best-effort SSRF preflight check."""
    try:
        resolve_and_validate_host(url)
        return True
    except SSRFProtectionError:
        return False


async def safe_request(
    method: str,
    url: str,
    *,
    timeout: httpx.Timeout | float | None = None,
    max_redirects: int = _MAX_REDIRECTS,
    client: httpx.AsyncClient | None = None,
    **kwargs,
) -> httpx.Response:
    """Execute an HTTP request with SSRF protections.

    Security properties:
    - validates scheme/host/port
    - resolves all A/AAAA answers
    - blocks private/internal/reserved targets
    - disables automatic redirects
    - manually follows redirects with revalidation
    """
    resolve_and_validate_host(url)

    request_timeout = timeout or _DEFAULT_TIMEOUT
    owns_client = client is None

    http_client = client or httpx.AsyncClient(
        timeout=request_timeout,
        follow_redirects=False,
    )

    try:
        current_url = url

        for redirect_count in range(max_redirects + 1):
            resolve_and_validate_host(current_url)

            response = await http_client.request(
                method,
                current_url,
                follow_redirects=False,
                **kwargs,
            )

            if not response.is_redirect:
                return response

            if redirect_count >= max_redirects:
                raise SSRFProtectionError("Too many redirects")

            location = response.headers.get("location")
            if not location:
                return response

            next_url = str(response.request.url.join(location))
            logger.info(
                "safe_request_follow_redirect",
                from_url=current_url,
                to_url=next_url,
                status_code=response.status_code,
            )
            current_url = next_url

        raise SSRFProtectionError("Redirect handling terminated unexpectedly")
    finally:
        if owns_client:
            await http_client.aclose()
