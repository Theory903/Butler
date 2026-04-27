"""
Butler-native web tools module.

Provides web search and extraction capabilities using direct API calls
instead of Hermes auxiliary_client and managed_tool_gateway.
This is a Butler-native implementation that replaces Hermes web_tools.py
to avoid deep Hermes dependencies.
"""

import logging
import os

import structlog

logger = structlog.get_logger(__name__)


def _get_backend_config() -> dict[str, str]:
    """Get web backend configuration from environment variables.

    Butler uses environment variables instead of Hermes CLI config.
    """
    return {
        "backend": os.getenv("WEB_BACKEND", "searxng").lower(),
        "tavily_api_key": os.getenv("TAVILY_API_KEY", ""),
        "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY", ""),
        "firecrawl_api_url": os.getenv("FIRECRAWL_API_URL", ""),
        "searxng_url": os.getenv("SEARXNG_URL", "http://searxng:8080"),
    }


def web_search_tool(
    query: str,
    limit: int = 5,
    search_depth: str = "basic",
) -> dict:
    """Search the web for information.

    Args:
        query: Search query
        limit: Maximum number of results (default: 5)
        search_depth: Search depth - "basic" or "advanced" (default: "basic")

    Returns:
        Dictionary with search results or error
    """
    config = _get_backend_config()
    backend = config["backend"]

    if backend == "searxng":
        return _searxng_search(query, limit, config)
    if backend == "tavily":
        return _tavily_search(query, limit, search_depth, config)
    if backend == "firecrawl":
        return _firecrawl_search(query, limit, config)
    return {"error": f"Unsupported web backend: {backend}"}


def _searxng_search(
    query: str,
    limit: int,
    config: dict[str, str],
) -> dict:
    """Search using the local SearXNG instance."""
    base_url = config.get("searxng_url", "").rstrip("/")
    if not base_url:
        return {"error": "SEARXNG_URL not set"}

    try:
        import httpx

        response = httpx.get(
            f"{base_url}/search",
            params={
                "q": query,
                "format": "json",
                "categories": "general",
            },
            timeout=15,
            headers={"User-Agent": "Butler/1.0"},
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", [])[:limit]:
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if not url:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "content": str(item.get("content", "") or "")[:2000],
                    "score": float(item.get("score", 0.0) or 0.0),
                }
            )

        answers = data.get("answers", [])
        answer_text = answers[0] if answers else ""

        logger.info(f"SearXNG search returned {len(results)} results for: {query}")
        return {
            "answer": answer_text,
            "results": results,
            "backend": "searxng",
        }

    except Exception as e:
        logger.error(f"SearXNG search failed: {e}")
        return {"error": f"Web search failed: {str(e)}"}


def _tavily_search(
    query: str,
    limit: int,
    search_depth: str,
    config: dict[str, str],
) -> dict:
    """Search using Tavily API.

    Args:
        query: Search query
        limit: Maximum results
        search_depth: Search depth
        config: Backend configuration

    Returns:
        Dictionary with search results or error
    """
    api_key = config["tavily_api_key"]
    if not api_key:
        return {"error": "TAVILY_API_KEY not set"}

    try:
        import httpx

        url = "https://api.tavily.com/search"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": limit,
            "search_depth": search_depth,
            "include_answer": True,
            "include_raw_content": False,
        }

        response = httpx.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        results = []
        for item in data.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0),
                }
            )

        return {
            "answer": data.get("answer", ""),
            "results": results,
            "backend": "tavily",
        }

    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return {"error": f"Web search failed: {str(e)}"}


def _firecrawl_search(
    query: str,
    limit: int,
    config: dict[str, str],
) -> dict:
    """Search using Firecrawl API.

    Args:
        query: Search query
        limit: Maximum results
        config: Backend configuration

    Returns:
        Dictionary with search results or error
    """
    api_key = config["firecrawl_api_key"]
    api_url = config.get("firecrawl_api_url", "https://api.firecrawl.dev")

    if not api_key:
        return {"error": "FIRECRAWL_API_KEY not set"}

    try:
        import httpx

        url = f"{api_url}/v1/search"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "query": query,
            "maxResults": limit,
            "searchOptions": {},
        }

        response = httpx.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        results = []
        if "data" in data:
            for item in data["data"]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("description", ""),
                        "markdown": item.get("markdown", ""),
                    }
                )

        return {
            "results": results,
            "backend": "firecrawl",
        }

    except Exception as e:
        logger.error(f"Firecrawl search failed: {e}")
        return {"error": f"Web search failed: {str(e)}"}


def web_extract_tool(
    urls: list[str],
    format: str = "markdown",
) -> dict:
    """Extract content from web pages.

    Args:
        urls: List of URLs to extract content from
        format: Output format - "markdown" or "html" (default: "markdown")

    Returns:
        Dictionary with extracted content or error
    """
    if not urls:
        return {"error": "No URLs provided"}

    config = _get_backend_config()
    backend = config["backend"]

    if backend == "firecrawl":
        return _firecrawl_extract(urls, format, config)
    return {"error": f"Extraction not supported for backend: {backend}"}


def _firecrawl_extract(
    urls: list[str],
    format: str,
    config: dict[str, str],
) -> dict:
    """Extract content using Firecrawl API.

    Args:
        urls: List of URLs
        format: Output format
        config: Backend configuration

    Returns:
        Dictionary with extracted content or error
    """
    api_key = config["firecrawl_api_key"]
    api_url = config.get("firecrawl_api_url", "https://api.firecrawl.dev")

    if not api_key:
        return {"error": "FIRECRAWL_API_KEY not set"}

    try:
        import httpx

        url = f"{api_url}/v1/scrape"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        results = []
        for target_url in urls:
            payload = {
                "url": target_url,
                "formats": [format],
            }

            response = httpx.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()

            if format == "markdown":
                content = data.get("data", {}).get("markdown", "")
            else:
                content = data.get("data", {}).get("html", "")

            results.append(
                {
                    "url": target_url,
                    "content": content,
                    "format": format,
                }
            )

        return {
            "results": results,
            "backend": "firecrawl",
        }

    except Exception as e:
        logger.error(f"Firecrawl extract failed: {e}")
        return {"error": f"Web extraction failed: {str(e)}"}
