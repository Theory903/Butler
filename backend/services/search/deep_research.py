import logging
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from domain.ml.contracts import IReasoningRuntime, ReasoningRequest
from domain.search.contracts import ISearchService
from services.search.service import EvidencePack, ExtractedContent

logger = logging.getLogger(__name__)

@dataclass
class ResearchStep:
    query: str
    rationale: str
    findings: str
    gap: Optional[str] = None

@dataclass
class DeepResearchResult:
    original_query: str
    summary: str
    steps: List[ResearchStep]
    all_evidence: List[ExtractedContent]
    completed: bool

class DeepResearchEngine:
    """Butler Deep Research Engine (v3.1).
    
    Implements a multi-hop reasoning loop for high-complexity queries.
    Cycle: Plan -> Search -> Extract -> Synthesize -> Check Gaps -> Repeat.
    """
    
    def __init__(
        self,
        ml_runtime: IReasoningRuntime,
        search_service: ISearchService,
        max_hops: int = 3
    ):
        self._ml = ml_runtime
        self._search = search_service
        self._max_hops = max_hops

    async def conduct_research(self, query: str, context: Optional[str] = None) -> DeepResearchResult:
        """Conduct thorough research on a given topic."""
        logger.info("deep_research_started", query=query)
        
        all_evidence = []
        steps = []
        current_knowledge = context or ""
        
        for hop in range(self._max_hops):
            # 1. Plan next step
            plan = await self._plan_research_step(query, current_knowledge, hop)
            if not plan.get("queries"):
                logger.info("deep_research_no_more_queries", hop=hop)
                break
                
            # 2. Execute parallel searches
            hop_evidence = []
            search_tasks = [self._search.search(q, mode="auto") for q in plan["queries"]]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            for res in search_results:
                if isinstance(res, EvidencePack):
                    hop_evidence.extend(res.results)
                    all_evidence.extend(res.results)
            
            # 3. Synthesize findings
            synthesis = await self._synthesize_step(query, current_knowledge, hop_evidence)
            
            step = ResearchStep(
                query=", ".join(plan["queries"]),
                rationale=plan.get("rationale", ""),
                findings=synthesis.get("summary", ""),
                gap=synthesis.get("gap")
            )
            steps.append(step)
            
            current_knowledge += f"\n\nStep {hop+1} Findings: {step.findings}"
            
            # 4. Check if we're done
            if not step.gap or "none" in step.gap.lower() or len(step.gap) < 5:
                logger.info("deep_research_completed_early", hop=hop)
                break
                
        # Final Synthesis
        final_summary = await self._final_synthesis(query, current_knowledge)
        
        return DeepResearchResult(
            original_query=query,
            summary=final_summary,
            steps=steps,
            all_evidence=all_evidence,
            completed=True
        )

    async def _plan_research_step(self, topic: str, knowledge: str, hop: int) -> Dict[str, Any]:
        """Ask LLM to plan the next set of search queries."""
        prompt = f"""
        Topic: {topic}
        Current Hop: {hop + 1}
        Current Knowledge: {knowledge[:3000]}
        
        Plan the next search queries to fill any information gaps.
        Return in JSON format:
        {{
            "rationale": "why these queries",
            "queries": ["query 1", "query 2"]
        }}
        """
        
        # Use T3 (Frontier) for planning
        req = ReasoningRequest(prompt=prompt)
        response = await self._ml.generate(req, preferred_tier="t3_frontier")
        if response and response.content:
            try:
                import json
                import re
                # Naive JSON extract if LLM returns markdown
                match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
        return {"queries": [topic] if hop == 0 else []}

    async def _synthesize_step(self, topic: str, knowledge: str, evidence: List[ExtractedContent]) -> Dict[str, Any]:
        """Summarize new evidence and identify remaining gaps."""
        evidence_text = "\n\n".join([f"Source: {e.url}\nContent: {e.content[:1000]}" for e in evidence[:3]])
        
        prompt = f"""
        Topic: {topic}
        Current Evidence:
        {evidence_text}
        
        Summarize what we just learned and identify what IS STILL MISSING (the gap).
        Return in JSON:
        {{
            "summary": "...",
            "gap": "..."
        }}
        """
        
        req = ReasoningRequest(prompt=prompt)
        response = await self._ml.generate(req, preferred_tier="t2_local")
        if response and response.content:
            try:
                import json
                import re
                match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
        return {"summary": "Failed to synthesize", "gap": "Unknown"}

    async def _final_synthesis(self, topic: str, knowledge: str) -> str:
        """Create the final comprehensive report."""
        prompt = f"""
        Topic: {topic}
        Aggregated Research:
        {knowledge}
        
        Produce a definitive, production-grade report on this topic. 
        Cite sources if possible. Use markdown for structure.
        """
        
        req = ReasoningRequest(prompt=prompt)
        response = await self._ml.generate(req, preferred_tier="t3_frontier")
        return response.content if response else "Failed to produce report."
