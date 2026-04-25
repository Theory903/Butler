import asyncio
from typing import Any

import structlog
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi

logger = structlog.get_logger(__name__)


class TransformationService:
    """Butler Research Ingestion and Transformation Engine."""

    def __init__(self, llm_runtime: Any = None):
        self._llm = llm_runtime

    async def ingest_url(self, url: str) -> dict[str, Any]:
        """Extract clean text from a web page."""
        try:
            downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
            content = await asyncio.to_thread(trafilatura.extract, downloaded)

            if not content:
                logger.warning("url_ingest_empty", url=url)
                return {"status": "error", "message": "No content extracted"}

            return {
                "status": "success",
                "content": content,
                "source_type": "web_page",
                "metadata": {"url": url},
            }
        except Exception as e:
            logger.error("url_ingest_failed", url=url, error=str(e))
            return {"status": "error", "message": str(e)}

    async def ingest_youtube(self, url: str) -> dict[str, Any]:
        """Extract transcript from a YouTube video."""
        try:
            video_id = self._extract_youtube_id(url)
            if not video_id:
                return {"status": "error", "message": "Invalid YouTube URL"}

            transcript_list = await asyncio.to_thread(YouTubeTranscriptApi.get_transcript, video_id)

            full_text = " ".join([t["text"] for t in transcript_list])

            return {
                "status": "success",
                "content": full_text,
                "source_type": "youtube_video",
                "metadata": {"url": url, "video_id": video_id},
            }
        except Exception as e:
            logger.error("youtube_ingest_failed", url=url, error=str(e))
            return {"status": "error", "message": str(e)}

    def _extract_youtube_id(self, url: str) -> str | None:
        """Extract video ID from various YouTube URL formats."""
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        if "youtu.be/" in url:
            return url.split("youtu.be/")[1].split("?")[0]
        return None

    async def generate_insight(self, content: str, goal: str) -> str:
        """Use LLM to transform raw content into a structured insight or note."""
        # This would call the LLM runtime with a specific research prompt
        f"Analyze the following content and extract key insights relevant to '{goal}':\n\n{content[:5000]}"

        # Simulated LLM transformation
        return f"AI-generated insight for goal '{goal}': Extracted key patterns and findings..."
