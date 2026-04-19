from dataclasses import dataclass
import trafilatura
from bs4 import BeautifulSoup
import httpx

@dataclass
class ExtractionResult:
    text: str
    method: str

class ContentExtractor:
    """Extract clean text from web pages."""
    
    async def _fetch(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    async def extract(self, url: str) -> ExtractionResult:
        html = None
        try:
            html = await self._fetch(url)
        except Exception:
            return ExtractionResult(text="", method="failed")

        # Primary: Trafilatura
        try:
            text = trafilatura.extract(html, include_links=True, include_tables=True)
            if text and len(text) > 100:
                return ExtractionResult(text=text, method="trafilatura")
        except Exception:
            pass
        
        # Fallback: BeautifulSoup
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            if text:
                return ExtractionResult(text=text, method="beautifulsoup")
        except Exception:
            pass
            
        return ExtractionResult(text="", method="failed")
