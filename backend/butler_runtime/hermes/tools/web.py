"""Butler-Hermes web tools.

Web operations from Hermes that have been assimilated into Butler with
SSRF protection and Butler governance.
"""

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class ButlerHermesWebTools:
    """Butler-native web tools from Hermes.

    Web operations with SSRF protection:
    - web_search: Search the web
    - web_extract: Extract content from a URL
    """

    def __init__(self, allow_private_urls: bool = False) -> None:
        """Initialize Butler web tools.

        Args:
            allow_private_urls: Whether to allow private network URLs
        """
        self._allow_private_urls = allow_private_urls

    def _is_safe_url(self, url: str) -> bool:
        """Check if a URL is safe (SSRF protection).

        Args:
            url: URL to check

        Returns:
            True if URL is safe, False otherwise
        """
        import socket

        try:
            parsed = urlparse(url)
            if not parsed.hostname:
                return False

            # Check for private IP addresses
            if not self._allow_private_urls:
                try:
                    ip = socket.gethostbyname(parsed.hostname)
                    private_ranges = [
                        ("10.0.0.0", "10.255.255.255"),
                        ("172.16.0.0", "172.31.255.255"),
                        ("192.168.0.0", "192.168.255.255"),
                        ("127.0.0.0", "127.255.255.255"),
                    ]
                    for start, end in private_ranges:
                        if ip >= start and ip <= end:
                            return False
                except socket.gaierror:
                    return False

            return True

        except Exception:
            return False

    async def web_search(self, query: str, num_results: int = 5) -> dict[str, Any]:
        """Search the web for information.

        Args:
            query: Search query
            num_results: Number of results to return

        Returns:
            Dictionary with search results or error

        Note: This is a stub. Real implementation would integrate with
        a search API (e.g., Tavily, Google, Bing, etc.)
        """
        try:
            # Stub implementation - in production, integrate with search API
            # For now, return a placeholder response
            return {
                "query": query,
                "results": [
                    {
                        "title": f"Search result for: {query}",
                        "url": "https://example.com",
                        "snippet": "This is a placeholder search result. Integrate with a real search API in production.",
                    }
                ],
                "num_results": 1,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Web search failed for query '{query}': {e}")
            return {
                "query": query,
                "results": [],
                "error": str(e),
            }

    async def web_extract(self, url: str, max_length: int = 10_000) -> dict[str, Any]:
        """Extract content from a URL.

        Args:
            url: URL to extract content from
            max_length: Maximum content length

        Returns:
            Dictionary with extracted content or error
        """
        try:
            # SSRF protection
            if not self._is_safe_url(url):
                return {
                    "url": url,
                    "content": None,
                    "error": "URL blocked by SSRF protection",
                }

            # Fetch content
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                content = response.text

                # Truncate if too long
                if len(content) > max_length:
                    content = content[:max_length] + "\n\n[...content truncated...]"

                return {
                    "url": url,
                    "content": content,
                    "content_length": len(content),
                    "status_code": response.status_code,
                    "error": None,
                }

        except httpx.HTTPStatusError as e:
            logger.exception(f"HTTP error extracting content from {url}: {e}")
            return {
                "url": url,
                "content": None,
                "error": f"HTTP error: {e.response.status_code}",
            }
        except Exception as e:
            logger.exception(f"Failed to extract content from {url}: {e}")
            return {
                "url": url,
                "content": None,
                "error": str(e),
            }
