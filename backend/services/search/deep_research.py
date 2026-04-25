from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningTier,
    ResponseFormat,
)
from domain.search.contracts import ISearchService, SearchEvidencePack, SearchResult

logger = logging.getLogger(__name__)


class ResearchPlan(BaseModel):
    """Structured plan for one deep-research hop."""

    model_config = ConfigDict(extra="forbid")

    rationale: str = ""
    queries: list[str] = Field(default_factory=list)


class StepSynthesis(BaseModel):
    """Structured synthesis for one hop."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    gap: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(frozen=True, slots=True)
class ResearchStep:
    query: str
    rationale: str
    findings: str
    gap: str | None = None
    evidence_count: int = 0


@dataclass(frozen=True, slots=True)
class DeepResearchResult:
    original_query: str
    summary: str
    steps: list[ResearchStep]
    all_evidence: list[SearchResult]
    completed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class DeepResearchEngine:
    """Butler Deep Research Engine.

    Multi-hop loop:
      1. Plan next search queries
      2. Execute bounded parallel searches
      3. Synthesize findings
      4. Decide whether more research is required
      5. Produce final report
    """

    def __init__(
        self,
        ml_runtime: IReasoningRuntime,
        search_service: ISearchService,
        max_hops: int = 3,
        max_queries_per_hop: int = 3,
        max_evidence_per_hop: int = 8,
        max_context_chars: int = 12_000,
        search_concurrency: int = 3,
    ) -> None:
        if max_hops <= 0:
            raise ValueError("max_hops must be greater than 0")
        if max_queries_per_hop <= 0:
            raise ValueError("max_queries_per_hop must be greater than 0")
        if max_evidence_per_hop <= 0:
            raise ValueError("max_evidence_per_hop must be greater than 0")
        if max_context_chars <= 0:
            raise ValueError("max_context_chars must be greater than 0")
        if search_concurrency <= 0:
            raise ValueError("search_concurrency must be greater than 0")

        self._ml = ml_runtime
        self._search = search_service
        self._max_hops = max_hops
        self._max_queries_per_hop = max_queries_per_hop
        self._max_evidence_per_hop = max_evidence_per_hop
        self._max_context_chars = max_context_chars
        self._search_semaphore = asyncio.Semaphore(search_concurrency)

    async def conduct_research(
        self,
        query: str,
        tenant_id: str,  # Required for multi-tenant isolation
        context: str | None = None,
    ) -> DeepResearchResult:
        """Conduct multi-hop research for a topic.

        Args:
            tenant_id: Required tenant UUID for multi-tenant isolation
        """
        normalized_query = (query or "").strip()
        if not normalized_query:
            return DeepResearchResult(
                original_query="",
                summary="No query provided.",
                steps=[],
                all_evidence=[],
                completed=True,
                metadata={
                    "hop_count": 0,
                    "evidence_count": 0,
                    "max_hops": self._max_hops,
                },
            )

        logger.info("deep_research_started", query=normalized_query)

        all_evidence: list[SearchResult] = []
        steps: list[ResearchStep] = []
        seen_evidence_keys: set[str] = set()
        current_knowledge = (context or "").strip()
        completed_early = False

        for hop in range(self._max_hops):
            plan = await self._plan_research_step(
                topic=normalized_query,
                knowledge=current_knowledge,
                hop=hop,
                tenant_id=tenant_id,
            )

            planned_queries = self._normalize_queries(plan.queries)
            if not planned_queries:
                logger.info("deep_research_no_more_queries", hop=hop)
                completed_early = True
                break

            hop_evidence = await self._run_searches(planned_queries)

            deduped_hop_evidence: list[SearchResult] = []
            for item in hop_evidence:
                evidence_key = self._evidence_key(item)
                if evidence_key in seen_evidence_keys:
                    continue
                seen_evidence_keys.add(evidence_key)
                deduped_hop_evidence.append(item)
                all_evidence.append(item)

            synthesis = await self._synthesize_step(
                topic=normalized_query,
                knowledge=current_knowledge,
                evidence=deduped_hop_evidence,
                tenant_id=tenant_id,
            )

            step = ResearchStep(
                query=", ".join(planned_queries),
                rationale=plan.rationale,
                findings=synthesis.summary,
                gap=synthesis.gap,
                evidence_count=len(deduped_hop_evidence),
            )
            steps.append(step)

            current_knowledge = self._merge_knowledge(
                current_knowledge=current_knowledge,
                step=step,
            )

            if self._is_research_complete(synthesis.gap):
                logger.info("deep_research_completed_early", hop=hop)
                completed_early = True
                break

        final_summary = await self._final_synthesis(
            topic=normalized_query,
            knowledge=current_knowledge,
            evidence=all_evidence,
            tenant_id=tenant_id,
        )

        return DeepResearchResult(
            original_query=normalized_query,
            summary=final_summary,
            steps=steps,
            all_evidence=all_evidence,
            completed=completed_early or len(steps) == self._max_hops,
            metadata={
                "hop_count": len(steps),
                "evidence_count": len(all_evidence),
                "max_hops": self._max_hops,
            },
        )

    async def _plan_research_step(
        self,
        *,
        topic: str,
        knowledge: str,
        hop: int,
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> ResearchPlan:
        """Ask the reasoning runtime to plan the next research hop."""
        prompt = (
            f"Topic:\n{topic}\n\n"
            f"Current hop: {hop + 1}\n\n"
            f"Current knowledge:\n{knowledge[: self._max_context_chars]}\n\n"
            "Plan the next search queries that would most effectively reduce uncertainty.\n"
            "Return JSON only with:\n"
            "{\n"
            '  "rationale": "why these queries",\n'
            '  "queries": ["query 1", "query 2"]\n'
            "}\n"
            f"Limit queries to at most {self._max_queries_per_hop}.\n"
        )

        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=(
                "You are Butler's deep-research planning engine.\n"
                "Generate precise multilingual-friendly web search queries.\n"
                "Avoid duplicates and overly broad phrasing.\n"
                "Return only valid JSON."
            ),
            max_tokens=500,
            temperature=0.1,
            response_format=ResponseFormat.JSON,
            metadata={"task": "deep_research_plan"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id=tenant_id,
                preferred_tier=ReasoningTier.T3,
            )
            return self._parse_model_json(response.content, ResearchPlan)
        except Exception:
            logger.exception("deep_research_plan_failed", topic=topic, hop=hop)

        return ResearchPlan(
            rationale="Fallback to original topic query.",
            queries=[topic] if hop == 0 else [],
        )

    async def _synthesize_step(
        self,
        *,
        topic: str,
        knowledge: str,
        evidence: list[SearchResult],
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> StepSynthesis:
        """Summarize what was learned in one hop and identify remaining gaps."""
        evidence_text = "\n\n".join(
            [
                f"Source: {item.url}\nTitle: {item.title}\nContent: {(item.content or item.snippet)[:1000]}"
                for item in evidence[: self._max_evidence_per_hop]
            ]
        )

        prompt = (
            f"Topic:\n{topic}\n\n"
            f"Existing knowledge:\n{knowledge[: self._max_context_chars]}\n\n"
            f"New evidence:\n{evidence_text}\n\n"
            "Summarize what was learned and identify what is still missing.\n"
            "Return JSON only with:\n"
            "{\n"
            '  "summary": "string",\n'
            '  "gap": "string or null",\n'
            '  "confidence": 0.0\n'
            "}\n"
        )

        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=(
                "You are Butler's research synthesis engine.\n"
                "Be concise, evidence-grounded, and explicit about gaps.\n"
                "Return only valid JSON."
            ),
            max_tokens=700,
            temperature=0.1,
            response_format=ResponseFormat.JSON,
            metadata={"task": "deep_research_synthesis"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id=tenant_id,
                preferred_tier=ReasoningTier.T2,
            )
            return self._parse_model_json(response.content, StepSynthesis)
        except Exception:
            logger.exception("deep_research_synthesis_failed", topic=topic)

        return StepSynthesis(
            summary="Synthesis failed for this hop.",
            gap="Unknown remaining gap.",
            confidence=0.0,
        )

    async def _final_synthesis(
        self,
        *,
        topic: str,
        knowledge: str,
        evidence: list[SearchResult],
        tenant_id: str,  # Required for multi-tenant isolation
    ) -> str:
        """Create the final report."""
        citation_block = "\n".join(
            [f"- {item.title} | {item.url}" for item in evidence[: self._max_evidence_per_hop]]
        )

        prompt = (
            f"Topic:\n{topic}\n\n"
            f"Aggregated research notes:\n{knowledge[: self._max_context_chars]}\n\n"
            f"Sources:\n{citation_block}\n\n"
            "Produce a definitive, structured markdown report.\n"
            "Ground the answer in the available evidence and mention uncertainty where relevant.\n"
        )

        request = ReasoningRequest(
            prompt=prompt,
            system_prompt=(
                "You are Butler's final research synthesis engine.\n"
                "Write a production-grade markdown report.\n"
                "Do not invent facts beyond the evidence provided."
            ),
            max_tokens=1500,
            temperature=0.2,
            response_format=ResponseFormat.MARKDOWN,
            metadata={"task": "deep_research_final_report"},
        )

        try:
            response = await self._ml.generate(
                request,
                tenant_id=tenant_id,
                preferred_tier=ReasoningTier.T3,
            )
            return response.content.strip() or "Failed to produce final report."
        except Exception:
            logger.exception("deep_research_final_synthesis_failed", topic=topic)
            return "Failed to produce final report."

    async def _run_searches(self, queries: list[str]) -> list[SearchResult]:
        """Run bounded parallel searches and flatten evidence."""
        results: list[SearchResult] = []

        async def _run_one(query: str) -> list[SearchResult]:
            async with self._search_semaphore:
                try:
                    pack = await self._search.search(query, mode="auto")
                    if isinstance(pack, SearchEvidencePack):
                        return list(pack.results)
                    return list(getattr(pack, "results", []))
                except Exception:
                    logger.exception("deep_research_search_failed", query=query)
                    return []

        # Structured concurrency is cleaner here than orbiting gather forever.
        task_results: list[list[SearchResult]] = []
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(_run_one(query)) for query in queries]
            for task in tasks:
                task_results.append(task.result())
        except Exception:
            logger.exception("deep_research_search_taskgroup_failed")
            return []

        for item_list in task_results:
            results.extend(item_list)

        return results

    def _normalize_queries(self, queries: list[str]) -> list[str]:
        """Trim, dedupe, and cap planned queries."""
        normalized: list[str] = []
        seen: set[str] = set()

        for query in queries:
            cleaned = re.sub(r"\s+", " ", query.strip())
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)
            if len(normalized) >= self._max_queries_per_hop:
                break

        return normalized

    def _merge_knowledge(
        self,
        *,
        current_knowledge: str,
        step: ResearchStep,
    ) -> str:
        section = (
            f"\n\nStep Findings:\n"
            f"Queries: {step.query}\n"
            f"Rationale: {step.rationale}\n"
            f"Findings: {step.findings}\n"
            f"Gap: {step.gap or 'None'}"
        )
        merged = f"{current_knowledge}{section}".strip()
        return merged[: self._max_context_chars]

    def _is_research_complete(self, gap: str | None) -> bool:
        if gap is None:
            return True

        normalized = gap.strip().lower()
        if not normalized:
            return True

        terminal_values = {
            "none",
            "no gap",
            "no major gap",
            "nothing significant",
            "complete",
        }
        return normalized in terminal_values or len(normalized) < 5

    def _parse_model_json(self, content: str, model_type: type[BaseModel]) -> BaseModel:
        """Parse model JSON robustly with fenced-code and object-span fallback."""
        raw = (content or "").strip()

        candidates: list[str] = []
        if raw:
            candidates.append(raw)

        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) >= 3:
                unfenced = "\n".join(lines[1:-1]).strip()
                if unfenced:
                    candidates.append(unfenced)

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            candidates.append(match.group())

        seen: set[str] = set()
        unique_candidates: list[str] = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)

        last_error: Exception | None = None
        for candidate in unique_candidates:
            try:
                return model_type.model_validate_json(candidate)
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc

        raise ValueError(f"Failed to parse structured model output: {last_error}")

    def _evidence_key(self, item: SearchResult) -> str:
        title = (item.title or "").strip().lower()
        url = (item.url or "").strip().lower()
        return f"{url}::{title}"
