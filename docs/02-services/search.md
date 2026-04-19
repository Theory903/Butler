# Search Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — All core phases implemented
> **Version:** 3.1  
> **Reference:** Butler evidence engine with crawler stack and hybrid retrieval  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Query Context** | ✅ IMPLEMENTED | Classification and rewriting |
| 2 | **Web Providers** | ✅ IMPLEMENTED | Tavily/SerpAPI/DDG — selected via `BUTLER_SEARCH_PROVIDER` env |
| 3 | **Extraction** | ✅ IMPLEMENTED | Trafilatura → BeautifulSoup → snippet fallback, parallelised |
| 4 | **Hybrid Retrieval** | ✅ ACTIVE | Dense + web blending via `ButlerWebSearchProvider` re-ranker |
| 5 | **Deep Research** | ✅ IMPLEMENTED | Multi-hop Plan→Search→Synthesise loop (v3.1) |
| 6 | **Crawler Stack** | 🔲 STUB | Playwright / Crawl4AI local nodes (Phase 3 roadmap) |

---

## 0.1 v3.1 Implementation Notes

> **Completed in v3.1 (2026-04-19)**

### Key Architectural Decisions
- **`SearchService` → `ButlerWebSearchProvider`**: The mock `search()` returning `[]` was replaced with a real provider abstraction. Provider selection (Tavily, SerpAPI, DuckDuckGo) is controlled by env; no code changes required to switch.
- **Parallel Extraction**: `ContentExtractor` calls are parallelised with `asyncio.gather`. Any URL that fails extraction falls back silently to the web snippet — no request fails hard.
- **DeepResearchEngine** (`services/search/deep_research.py`): Multi-hop loop capped at 3 iterations. Each hop: plan sub-queries → parallel search → synthesise partial answer → extract gaps → repeat if confidence < 0.85.
- **Circular Import Guard**: `deep_research.py` imports `SearchService`, which previously caused a circular import. Resolved via `TYPE_CHECKING` guard in `service.py` and lazy `_ensure_deep_engine()` on first use.

### Key Files
| File | Role |
|------|------|
| `services/search/service.py` | Evidence engine — coordinates extraction and provider |
| `services/search/web_provider.py` | Sovereign search abstraction (multi-backend) |
| `services/search/extraction.py` | Trafilatura → BS4 → snippet fallback |
| `services/search/deep_research.py` | Multi-hop research engine **[NEW v3.1]** |
| `services/search/answering_engine.py` | Final synthesis layer |

---

## 1. Service Overview

### 1.1 Purpose
The Search service is Butler's **external retrieval and evidence pipeline**. It provides:
- Query understanding and planning
- Provider-aware retrieval (web, URL, internal)
- Content fetch and extraction via crawler stack
- Hybrid retrieval (dense + sparse + metadata filters)
- Reranking
- Evidence-pack construction with citations
- Provenance preservation

This is NOT "RAG with a shovel." It's an evidence engine with standards.

### 1.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Butler Evidence Engine                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: User Query                                                      │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ QUERY UNDERSTANDING                                         │   │
│  │  • Classify query mode                                     │   │
│  │  • Extract features (freshness, official, site)           │   │
│  │  • Rewrite ambiguous queries                              │   │
│  │  • Decompose multi-hop questions                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                                                              │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐            │   │
│  │  │ Direct URL │  │Internal   │  │ Playwright│            │   │
│  │  │ Fetch     ���  │ Qdrant    │  │ JS Fallback│            │   │
│  │  └────────────┘  └────────────┘  └────────────┘            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ CRAWL EXTRACTION PIPELINE                                 │   │
│  │                                                              │   │
│  │  HTTP Fetch ──► Trafilatura ──► Metadata ──► Clean        │   │
│  │       │                                                      │   │
│  │  Crawl4AI ──► Extracted Content                            │   │
│  │       │                                                      │   │
│  │  Playwright ──► Rendered DOM ──► Extractor                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ HYBRID RETRIEVAL + RERANKING                        │   │
│  │  • Dense embeddings                                       │   │
│  │  • Sparse/BM25                                            │   │
│  │  • Metadata filters                                       │   │
│  │  • Freshness + trust scoring                              │   │
│  │  • Heavy reranker                                        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  OUTPUT: Evidence Pack                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Boundaries

| Service | Boundary |
|---------|----------|
| Search | Evidence only - never generates final answer |
| Orchestrator | Consumes evidence, generates final response |
| Memory | Stores indexed content, not Search |
| ML | Generates embeddings for retrieval |

### 1.4 Hermes Library Integration
Search treats Hermes as **deferred capability source**:
- Firecrawl / crawler integrations
- Browser skills
- Research skills

Current: Own query/extraction contracts.

---

## 2. Query Understanding

### 2.1 Query Classification

```python
from enum import Enum

class QueryMode(str, Enum):
    WEB = "web"                    # General web search
    URL_FETCH = "url_fetch"        # Direct URL extraction
    INTERNAL = "internal"          # Butler knowledge base
    HYBRID = "hybrid"             # Combined检索
    RESEARCH = "research"         # Deep multi-hop research
    COMPARISON = "comparison"    # A vs B analysis
    FRESH_NEWS = "fresh_news"   # Time-sensitive

@dataclass
class QueryFeatures:
    normalized_query: str
    rewritten_queries: list[str]
    mode: QueryMode
    freshness_required: bool
    official_source_preferred: bool
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None
    top_k: int = 10
    language: str | None = None
    time_horizon: str | None = None  # last_24h, last_week, etc.
```

### 2.2 Query Rewriting

```python
class QueryRewriter:
    async def rewrite(self, query: str) -> list[str]:
        """Expand and improve queries"""
        
        rewrites = [query]
        
        # Expand abbreviations
        rewrites.extend(self.expand_abbreviations(query))
        
        # Add freshness hints if needed
        rewrites.extend(self.add_freshness(query))
        
        # Rewrite vague terms
        rewrites.extend(self.rewrite_vague(query))
        
        return list(set(rewrites))  # Dedupe
```

---

## 3. Crawl Provider Layer

### 3.1 Provider Classes

```python
from enum import Enum

class ProviderType(str, Enum):
    FULL_SEARCH = "full_search"      # Google, Bing
    INSTANT_ANSWER = "instant_answer"  # DuckDuckGo
    DIRECT_FETCH = "direct_fetch"    # Plain HTTP
    CRAWL_ENGINE = "crawl_engine"   # Crawl4AI, Firecrawl
    BROWSER_RENDER = "browser_render"  # Playwright
    INTERNAL = "internal"          # Qdrant

@dataclass
class CrawlRequest:
    url: str
    mode: str  # article, domain_crawl, browser_render
    extract_markdown: bool = True
    timeout_ms: int = 30000

@dataclass
class CrawlResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    markdown: str | None = None
    html: str | None = None
    metadata: dict = {}
    error: str | None = None
```

### 3.2 Crawl4AI Integration

```python
class Crawl4AIProvider:
    """[STUB] Primary open crawler"""
    
    async def crawl(self, request: CrawlRequest) -> CrawlResult:
        result = await self.crawl4ai.crawl(
            url=request.url,
            extractMarkdown=request.extract_markdown,
            timeout=request.timeout_ms / 1000
        )
        
        return CrawlResult(
            url=request.url,
            final_url=result.url,
            status_code=200,
            content_type="text/html",
            markdown=result.markdown,
            metadata=result.metadata
        )
```

### 3.3 Firecrawl Integration

```python
class FirecrawlProvider:
    """Site-wide crawl and scrape layer"""
    
    async def map(self, url: str) -> list[str]:
        """Discover all URLs on domain"""
        return await self.firecrawl.map(url)
    
    async def scrape(self, url: str, mode: str = "markdown") -> CrawlResult:
        result = await self.firecrawl.scrape(url, mode=mode)
        
        return CrawlResult(
            url=url,
            final_url=result.url,
            status_code=200,
            markdown=result.markdown,
            metadata=result.metadata
        )
```

### 3.4 Playwright Fallback

```python
class PlaywrightProvider:
    """JS-heavy / interactive page fallback"""
    
    async def render_fetch(self, url: str) -> CrawlResult:
        """Render page with JS, then extract"""
        
        async with self.browser.new_page() as page:
            await page.goto(url, wait_until="networkidle")
            
            # Extract rendered content
            content = await page.content()
            markdown = await page.evaluate("""
                () => {
                    // Use Reader mode if available
                    return document.body.innerText;
                }
            """)
            
            return CrawlResult(
                url=url,
                final_url=page.url,
                status_code=200,
                html=content,
                markdown=markdown
            )
```

### 3.5 Provider Routing

```python
class CrawlRouter:
    """Route to appropriate crawl provider"""
    
    async def route(self, url: str) -> CrawlResult:
        # 1. Static article → HTTP + Trafilatura
        if await self.is_static_article(url):
            return await self.http_provider.crawl(url)
        
        # 2. Docs/site → Crawl4AI
        if await self.is_docs_site(url):
            return await self.crawl4ai.crawl(url)
        
        # 3. Site-wide → Firecrawl
        if await self.is_full_crawl(url):
            return await self.firecrawl.scrape(url)
        
        # 4. JS-heavy → Playwright
        if await self.is_js_heavy(url):
            return await self.playwright.render_fetch(url)
        
        # Default → Crawl4AI
        return await self.crawl4ai.crawl(url)
```

---

## 4. Extraction Pipeline

### 4.1 Trafilatura Integration

```python
class ContentExtractor:
    """Primary content extraction"""
    
    async def extract(self, html: str, url: str) -> ExtractedDocument:
        # Use Trafilatura for main content
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            output_format="python"
        )
        
        return ExtractedDocument(
            url=url,
            title=result.title,
            author=result.author,
            published_at=result.date,
            text=result.text,
            images=result.images or [],
            language=result.language,
            extraction_method="trafilatura"
        )
```

### 4.2 Extracted Document Schema

```python
@dataclass
class ExtractedDocument:
    url: str
    canonical_url: str | None
    title: str | None
    author: str | None
    published_at: datetime | None
    text: str
    images: list[str]
    language: str | None
    extraction_method: str  # trafilatura, playwright_fallback, etc.
    extraction_quality_score: float
```

### 4.3 Chunking

```python
class EvidenceChunker:
    """Split content into evidence chunks"""
    
    async def chunk(
        self, 
        document: ExtractedDocument,
        max_tokens: int = 500,
        overlap: int = 50
    ) -> list[EvidenceChunk]:
        """Chunk by headings/sections"""
        
        chunks = []
        
        # Split by headings
        sections = self.split_by_headings(document.text)
        
        for section in sections:
            tokens = self.count_tokens(section.text)
            
            if tokens > max_tokens:
                # Sub-chunk
                sub_chunks = self.token_chunk(section.text, max_tokens, overlap)
                chunks.extend(sub_chunks)
            else:
                chunks.append(EvidenceChunk(
                    chunk_id=uuid4(),
                    source_id=document.url,
                    text=section.text,
                    heading_path=section.heading_path,
                    token_count=tokens
                ))
        
        return chunks
```

---

## 5. Fetch Policy & Safety

### 5.1 Fetch Policy

```python
@dataclass
class FetchPolicy:
    obey_robots: bool = True
    max_concurrency_per_domain: int = 2
    min_delay_ms_per_domain: int = 1000
    request_timeout_ms: int = 8000
    max_redirects: int = 5
    max_html_size_bytes: int = 5_000_000

class SSRFProtection:
    """Prevent SSRF attacks"""
    
    async def validate(self, url: str) -> bool:
        parsed = urlparse(url)
        
        # Block private IPs
        if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
            return False
        
        # Block metadata endpoints
        if "169.254.169.254" in parsed.hostname:
            return False
        
        # Only http/https
        if parsed.scheme not in ["http", "https"]:
            return False
        
        return True
```

### 5.2 Rate Limiting

```python
class DomainRateLimiter:
    """Per-domain rate limits"""
    
    async def acquire(self, domain: str) -> bool:
        # Check Redis counter
        count = await self.redis.get(f"rate:{domain}")
        
        if count and count >= self.max_requests_per_window:
            return False
        
        # Increment
        await self.redis.incr(f"rate:{domain}")
        await self.redis.expire(f"rate:{domain}", self.window_seconds)
        
        return True
```

---

## 6. Hybrid Retrieval

### 6.1 Retrieval Architecture

```python
class HybridRetrieval:
    """Dense + Sparse + Metadata filtering"""
    
    async def retrieve(
        self, 
        query: str, 
        top_k: int = 20,
        filters: dict | None = None
    ) -> list[EvidenceChunk]:
        
        # Dense search
        dense_results = await self.dense_search(query, limit=50)
        
        # Sparse/BM25 search
        sparse_results = await self.sparse_search(query, limit=50)
        
        # Merge candidates with scoring
        merged = self.merge_candidates(
            dense_results, 
            sparse_results,
            alpha=0.5,  # Dense weight
            beta=0.3,   # Sparse weight  
            gamma=0.2   # Freshness weight
        )
        
        # Apply metadata filters
        if filters:
            merged = self.apply_filters(merged, filters)
        
        # Rerank with heavy model
        reranked = await self.reranker.rerank(query, merged[:50])
        
        return reranked[:top_k]
```

### 6.2 Ranking Signals

| Signal | Weight | Source |
|--------|--------|--------|
| Semantic relevance | 0.4 | Dense embedding |
| Lexical match | 0.3 | BM25 |
| Freshness | 0.15 | published_at |
| Source trust | 0.1 | Domain reputation |
| Extraction quality | 0.05 | Trafilatura score |

### 6.3 Trust Scoring

```python
class TrustScorer:
    """Compute source trust score"""
    
    async def score(self, document: ExtractedDocument) -> float:
        score = 0.5  # Base
        
        # Domain reputation
        if document.domain in self.known_trusted_domains:
            score += 0.3
        
        # Metadata presence
        if document.author:
            score += 0.1
        if document.published_at:
            score += 0.1
        
        # Extraction quality
        score += document.extraction_quality_score * 0.1
        
        return min(score, 1.0)
```

---

## 7. Research Mode

### 7.1 Multi-Hop Retrieval

```python
class ResearchMode:
    """Deep research with decomposition"""
    
    async def research(
        self,
        query: str,
        depth: int = 2
    ) -> ResearchPack:
        
        # Decompose query
        sub_queries = await self.decompose(query)
        
        all_sources = []
        all_chunks = []
        
        # Iterative retrieval
        for sub_query in sub_queries:
            results = await self.retrieve(sub_query)
            all_sources.extend(results.sources)
            all_chunks.extend(results.chunks)
        
        # Find contradictions
        contradictions = self.find_contradictions(all_chunks)
        
        return ResearchPack(
            sources=all_sources,
            chunks=all_chunks,
            sub_queries=sub_queries,
            contradictions=contradictions
        )
```

### 7.2 Comparison Mode

```python
class ComparisonMode:
    """A vs B analysis"""
    
    async def compare(
        self,
        query_a: str,
        query_b: str,
        criteria: list[str]
    ) -> ComparisonPack:
        
        results_a = await self.retrieve(query_a)
        results_b = await self.retrieve(query_b)
        
        # Find common claims
        common = self.find_common_claims(results_a.chunks, results_b.chunks)
        
        # Find conflicts
        conflicts = self.find_conflicts(results_a.chunks, results_b.chunks)
        
        return ComparisonPack(
            sources_a=results_a.sources,
            sources_b=results_b.sources,
            common_claims=common,
            conflicting_claims=conflicts
        )
```

---

## 8. Evidence Pack Output

### 8.1 Evidence Pack Schema

```python
@dataclass
class EvidencePack:
    """Return evidence, NOT final answer"""
    
    query: str
    rewritten_queries: list[str]
    sources: list[SourceDocument]
    chunks: list[EvidenceChunk]
    citations: list[Citation]
    retrieval_metadata: dict
    
@dataclass  
class SourceDocument:
    source_id: str
    url: str
    canonical_url: str | None
    title: str | None
    domain: str
    published_at: datetime | None
    fetched_at: datetime
    trust_score: float
    freshness_score: float
    
@dataclass
class Citation:
    source_id: str
    url: str
    title: str | None
    chunk_ids: list[str]
    evidence_spans: list[dict]
```

---

## 9. API Contracts

### 9.1 Query Plan

```yaml
POST /search/query-plan
  Request:
    { "query": "string", "mode": "auto" }
  Response:
    {
      "normalized_query": "...",
      "rewritten_queries": ["...", "..."],
      "mode": "hybrid",
      "freshness_required": true,
      "official_source_preferred": false
    }
```

### 9.2 Web Search

```yaml
POST /search/web
  Request:
    { "query": "string", "limit": 10, "provider": "google" }
  Response:
    { "results": [...] }
```

### 9.3 URL Fetch + Extract

```yaml
POST /search/fetch
  Request:
    { "url": "https://..." }
  Response:
    {
      "source": { "url": "...", "title": "...", "domain": "..." },
      "document": { "text": "...", "published_at": "...", "quality": 0.9 }
    }
```

### 9.4 Evidence Retrieval

```yaml
POST /search/retrieve
  Request:
    { "query": "string", "top_k": 10, "mode": "hybrid" }
  Response:
    {
      "sources": [...],
      "chunks": [...],
      "citations": [...]
    }
```

### 9.5 Research

```yaml
POST /search/research
  Request:
    { "query": "string", "depth": 2 }
  Response:
    {
      "sources": [...],
      "chunks": [...],
      "sub_queries": [...],
      "contradictions": [...]
    }
```

### 9.6 Compare

```yaml
POST /search/compare
  Request:
    { 
      "query_a": "postgres logical replication",
      "query_b": "postgres physical replication",
      "criteria": ["setup complexity", "latency"]
    }
  Response:
    {
      "topic_a_sources": [...],
      "topic_b_sources": [...],
      "common_claims": [...],
      "conflicting_claims": [...]
    }
```

---

## 10. Observability

### 10.1 Metrics

| Metric | Type | Labels |
|-------|------|--------|
| search.provider_request_total | counter | provider, status |
| search.fetch_latency_seconds | histogram | domain |
| search.extraction_success_total | counter | method |
| search.retrieval_latency_seconds | histogram | mode |
| search.rerank_latency_seconds | histogram | model |
| search.duplicate_source_rate | gauge | - |
| search.citation_coverage_rate | gauge | - |

### 10.2 Attributes

Required OTel attributes:
- `service.name`
- `butler.query_mode`
- `butler.provider`
- `butler.domain`
- `butler.top_k`
- `butler.reranker`

---

## 11. Error Codes (RFC 9457)

| Code | Error | HTTP | Cause |
|------|-------|------|-------|
| S001 | query-invalid | 400 | Invalid query |
| S002 | fetch-blocked | 403 | SSRF/robots blocking |
| S003 | fetch-timeout | 504 | Domain timeout |
| S004 | extraction-failed | 502 | Content parse error |
| S005 | provider-error | 502 | External provider |
| S006 | rate-limited | 429 | Domain rate limit |

---

## 12. Runbook

### 12.1 Poor Extraction

```bash
# Check extraction method
curl http://search:8012/metrics | grep extraction

# Fall back to Trafilatura
# Inspect extraction_quality_score
# Enable Playwright fallback for JS sites
```

### 12.2 Low Recall

```bash
# Increase sparse pool
# Enable query rewrite
# Check domain filters
# Widen top_k
```

### 12.3 Duplicate Results

```bash
# Normalize canonical URLs
# Apply domain diversity penalty
# Check deduplication logic
```

---

## 13. Stack Summary

| Layer | Primary | Fallback |
|-------|---------|----------|
| **Web Search** | Google Programmable Search | DuckDuckGo |
| **Crawler** | Crawl4AI | Firecrawl |
| **Browser** | - | Playwright |
| **Extractor** | Trafilatura | Custom cleanup |
| **Retrieval** | Qdrant (dense) | BM25 (sparse) |
| **Reranker** | Cross-encoder | None |
| **Internal** | Qdrant | BM25 |

**Gold rule:** Evidence first, answer second. Search returns pack, not verdict.

---

*Document owner: Search Team*  
*Version: 2.0 (Implementation-ready)*  
*Last updated: 2026-04-18*