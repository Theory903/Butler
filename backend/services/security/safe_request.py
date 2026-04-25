"""
Safe Request - SSRF-Safe HTTP Client

Production-grade HTTP client with SSRF prevention.
All outbound HTTP requests from tools must use this client.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from services.security.egress_policy import EgressDecision, EgressPolicy

logger = structlog.get_logger(__name__)


class SafeRequestError(Exception):
    """Raised when safe request is denied."""


class SafeRequestClient:
    """
    SSRF-safe HTTP client with egress policy enforcement.

    All outbound HTTP requests from tools must go through this client.
    Enforces egress policy before allowing requests.
    """

    def __init__(
        self,
        *,
        egress_policy: EgressPolicy | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        """
        Initialize safe request client.

        Args:
            egress_policy: Egress policy to enforce. If None, uses default.
            timeout: HTTP timeout. If None, uses sensible default.
        """
        self._egress_policy = egress_policy or EgressPolicy.get_default()
        self._timeout = timeout or httpx.Timeout(
            connect=10.0,
            read=60.0,
            write=10.0,
            pool=5.0,
        )
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def get(
        self,
        url: str,
        tenant_id: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        """
        Perform safe GET request with egress policy enforcement.

        Args:
            url: URL to request
            tenant_id: Tenant UUID for egress policy
            headers: Optional request headers
            params: Optional query parameters
            follow_redirects: Whether to follow redirects (re-checks egress policy)

        Returns:
            HTTP response

        Raises:
            SafeRequestError: If egress policy denies request
            httpx.HTTPError: If HTTP request fails
        """
        return await self._request(
            "GET",
            url,
            tenant_id,
            headers=headers,
            params=params,
            follow_redirects=follow_redirects,
        )

    async def post(
        self,
        url: str,
        tenant_id: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        """
        Perform safe POST request with egress policy enforcement.

        Args:
            url: URL to request
            tenant_id: Tenant UUID for egress policy
            headers: Optional request headers
            json: Optional JSON body
            data: Optional data body
            follow_redirects: Whether to follow redirects (re-checks egress policy)

        Returns:
            HTTP response

        Raises:
            SafeRequestError: If egress policy denies request
            httpx.HTTPError: If HTTP request fails
        """
        return await self._request(
            "POST",
            url,
            tenant_id,
            headers=headers,
            json=json,
            data=data,
            follow_redirects=follow_redirects,
        )

    async def _request(
        self,
        method: str,
        url: str,
        tenant_id: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any | None = None,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        """
        Internal request method with egress policy enforcement.

        Args:
            method: HTTP method
            url: URL to request
            tenant_id: Tenant UUID for egress policy
            headers: Optional request headers
            params: Optional query parameters
            json: Optional JSON body
            data: Optional data body
            follow_redirects: Whether to follow redirects

        Returns:
            HTTP response

        Raises:
            SafeRequestError: If egress policy denies request
            httpx.HTTPError: If HTTP request fails
        """
        # Check egress policy for initial URL
        decision, reason = self._egress_policy.check_url(url, tenant_id)
        if decision == EgressDecision.DENY:
            raise SafeRequestError(f"Egress policy denied: {reason}")

        # Perform request
        response = await self._client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
            data=data,
            follow_redirects=False,  # Handle redirects manually to re-check policy
        )

        # Handle redirects with egress policy re-check
        if follow_redirects and response.is_redirect:
            redirect_url = response.headers.get("location")
            if redirect_url:
                # Check egress policy for redirect URL
                redirect_decision, redirect_reason = self._egress_policy.check_url(
                    redirect_url, tenant_id
                )
                if redirect_decision == EgressDecision.DENY:
                    raise SafeRequestError(f"Egress policy denied redirect: {redirect_reason}")

                # Follow redirect
                response = await self._client.request(
                    method=method,
                    url=redirect_url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    follow_redirects=False,
                )

        logger.info(
            "safe_request_completed",
            tenant_id=tenant_id,
            method=method,
            url=url,
            status_code=response.status_code,
        )

        return response

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> SafeRequestClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
