import httpx
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = structlog.get_logger(__name__)

class SearxNGAdapter:
    """Adapter for local SearxNG search engine."""
    
    def __init__(self, base_url: str = "http://searxng:8080"):
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=10.0)

    async def search(self, query: str, categories: List[str] = ["general"], engines: List[str] = [], language: str = "en-US") -> List[Dict[str, Any]]:
        """Perform search against SearxNG."""
        params = {
            "q": query,
            "format": "json",
            "categories": ",".join(categories),
            "language": language,
        }
        if engines:
            params["engines"] = ",".join(engines)

        try:
            response = await self._client.get(f"{self._base_url}/search", params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            logger.info("searxng_search_success", query=query, result_count=len(results))
            
            # Map to unified Butler search result format
            return [
                {
                    "url": r.get("url"),
                    "title": r.get("title"),
                    "content": r.get("content"),
                    "snippet": r.get("snippet"),
                    "engine": r.get("engine"),
                    "score": r.get("score"),
                    "published_date": self._parse_date(r.get("publishedDate"))
                }
                for r in results
            ]
        except Exception as exc:
            logger.error("searxng_search_failed", query=query, error=str(exc))
            return []

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            return None

    async def close(self):
        await self._client.aclose()
