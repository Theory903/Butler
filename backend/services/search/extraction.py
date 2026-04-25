from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import httpx
import structlog
import trafilatura
from bs4 import BeautifulSoup

from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(
    connect=5.0,
    read=15.0,
    write=5.0,
    pool=5.0,
)

_DEFAULT_LIMITS: Final[httpx.Limits] = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
)

_BLOCKED_TAGS: Final[tuple[str, ...]] = (
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "svg",
    "canvas",
    "form",
)

_MIN_PRIMARY_TEXT_LEN: Final[int] = 120
_MIN_FALLBACK_TEXT_LEN: Final[int] = 80
_MAX_EXTRACTED_CHARS: Final[int] = 100_000
_MAX_FETCHED_HTML_CHARS: Final[int] = 2_000_000

_ALLOWED_CONTENT_TYPE_PREFIXES: Final[tuple[str, ...]] = (
    "text/html",
    "application/xhtml+xml",
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str
    method: str
    fetched_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    error: str | None = None


class ContentExtractor:
    """Extract clean text from web pages for Butler search/research flows.

    Design goals:
    - reuse one AsyncClient for connection pooling
    - prefer Trafilatura for main-content extraction
    - fall back to simpler extraction paths when needed
    - return explicit extraction metadata for observability/debugging
    """

    def __init__(
        self,
        *,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
        limits: httpx.Limits = _DEFAULT_LIMITS,
        follow_redirects: bool = True,
        min_primary_text_len: int = _MIN_PRIMARY_TEXT_LEN,
        min_fallback_text_len: int = _MIN_FALLBACK_TEXT_LEN,
        max_extracted_chars: int = _MAX_EXTRACTED_CHARS,
        max_fetched_html_chars: int = _MAX_FETCHED_HTML_CHARS,
        bs4_parser: str = "html.parser",
        tenant_id: str | None = None,
    ) -> None:
        if min_primary_text_len <= 0:
            raise ValueError("min_primary_text_len must be greater than 0")
        if min_fallback_text_len <= 0:
            raise ValueError("min_fallback_text_len must be greater than 0")
        if max_extracted_chars <= 0:
            raise ValueError("max_extracted_chars must be greater than 0")
        if max_fetched_html_chars <= 0:
            raise ValueError("max_fetched_html_chars must be greater than 0")
        if not bs4_parser.strip():
            raise ValueError("bs4_parser must not be empty")

        self._tenant_id = tenant_id
        self._safe_client = SafeRequestClient(timeout=timeout) if tenant_id else None
        # Fallback to direct httpx for non-tenant contexts (e.g., system-level extraction)
        self._client = httpx.AsyncClient(
            follow_redirects=follow_redirects,
            timeout=timeout,
            limits=limits,
            headers={
                "User-Agent": (
                    "ButlerSearchExtractor/1.0 (compatible; Butler; +https://butler.lasmoid.ai)"
                )
            },
        )
        self._min_primary_text_len = min_primary_text_len
        self._min_fallback_text_len = min_fallback_text_len
        self._max_extracted_chars = max_extracted_chars
        self._max_fetched_html_chars = max_fetched_html_chars
        self._bs4_parser = bs4_parser
        self._closed = False

    async def __aenter__(self) -> ContentExtractor:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def _fetch(self, url: str) -> tuple[str, str, int | None, str | None]:
        self._ensure_open()

        if self._safe_client and self._tenant_id:
            response = await self._safe_client.get(url, tenant_id=self._tenant_id)
        else:
            response = await self._client.get(url)
        response.raise_for_status()

        html = response.text
        if len(html) > self._max_fetched_html_chars:
            html = html[: self._max_fetched_html_chars]

        return (
            str(response.url),
            html,
            response.status_code,
            response.headers.get("content-type"),
        )

    async def extract(self, url: str) -> ExtractionResult:
        self._ensure_open()

        html: str
        fetched_url: str
        status_code: int | None
        content_type: str | None

        try:
            fetched_url, html, status_code, content_type = await self._fetch(url)
        except Exception as exc:
            logger.warning("content_extractor_fetch_failed", url=url, error=str(exc))
            return ExtractionResult(
                text="",
                method="fetch_failed",
                fetched_url=None,
                status_code=None,
                content_type=None,
                error=str(exc),
            )

        if not self._is_supported_content_type(content_type):
            logger.debug(
                "content_extractor_unsupported_content_type",
                url=fetched_url,
                content_type=content_type,
            )
            return ExtractionResult(
                text="",
                method="unsupported_content_type",
                fetched_url=fetched_url,
                status_code=status_code,
                content_type=content_type,
                error="Response content type is not supported for HTML text extraction",
            )

        text = self._extract_with_trafilatura(html, fetched_url)
        if len(text) >= self._min_primary_text_len:
            return ExtractionResult(
                text=text,
                method="trafilatura_extract",
                fetched_url=fetched_url,
                status_code=status_code,
                content_type=content_type,
            )

        text = self._extract_with_trafilatura_baseline(html)
        if len(text) >= self._min_fallback_text_len:
            return ExtractionResult(
                text=text,
                method="trafilatura_baseline",
                fetched_url=fetched_url,
                status_code=status_code,
                content_type=content_type,
            )

        text = self._extract_with_trafilatura_html2txt(html)
        if len(text) >= self._min_fallback_text_len:
            return ExtractionResult(
                text=text,
                method="trafilatura_html2txt",
                fetched_url=fetched_url,
                status_code=status_code,
                content_type=content_type,
            )

        text = self._extract_with_bs4(html)
        if len(text) >= self._min_fallback_text_len:
            return ExtractionResult(
                text=text,
                method="beautifulsoup_text",
                fetched_url=fetched_url,
                status_code=status_code,
                content_type=content_type,
            )

        logger.debug("content_extractor_no_text", url=fetched_url, status_code=status_code)
        return ExtractionResult(
            text="",
            method="failed",
            fetched_url=fetched_url,
            status_code=status_code,
            content_type=content_type,
            error="No sufficient text could be extracted",
        )

    def _extract_with_trafilatura(self, html: str, url: str) -> str:
        try:
            text = trafilatura.extract(
                html,
                url=url,
                include_links=False,
                include_tables=True,
                include_comments=False,
                favor_precision=True,
            )
            return self._clean_text(text or "")
        except Exception as exc:
            logger.debug("trafilatura_extract_failed", url=url, error=str(exc))
            return ""

    def _extract_with_trafilatura_baseline(self, html: str) -> str:
        try:
            _body, text, _length = trafilatura.baseline(html)
            return self._clean_text(text or "")
        except Exception as exc:
            logger.debug("trafilatura_baseline_failed", error=str(exc))
            return ""

    def _extract_with_trafilatura_html2txt(self, html: str) -> str:
        try:
            text = trafilatura.html2txt(html, clean=True)
            return self._clean_text(text or "")
        except Exception as exc:
            logger.debug("trafilatura_html2txt_failed", error=str(exc))
            return ""

    def _extract_with_bs4(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, self._bs4_parser)

            for tag in soup(_BLOCKED_TAGS):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            return self._clean_text(text)
        except Exception as exc:
            logger.debug("beautifulsoup_extract_failed", parser=self._bs4_parser, error=str(exc))
            return ""

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        normalized = normalized.strip()

        if len(normalized) > self._max_extracted_chars:
            return normalized[: self._max_extracted_chars]

        return normalized

    def _is_supported_content_type(self, content_type: str | None) -> bool:
        if content_type is None:
            return True

        normalized = content_type.split(";", 1)[0].strip().lower()
        return any(normalized.startswith(prefix) for prefix in _ALLOWED_CONTENT_TYPE_PREFIXES)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("ContentExtractor has been closed")
