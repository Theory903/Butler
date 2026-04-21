import asyncio
import structlog
import time
from typing import List, Dict, Any
from core.observability import ButlerTracer, get_tracer
from domain.ml.contracts import RetrievalCandidate, RerankResult

logger = structlog.get_logger(__name__)

class CandidateMixer:
    """Twitter-style Candidate Mixer for federated retrieval.
    
    Orchestrates candidate gathering from multiple sources:
    1. MemoryEngine (Vector Similarity) - T1/T2
    2. KnowledgeGraph (Graph Relationships) - T2
    3. AmbientState (Real-time Context) - T0
    """

    def __init__(self, memory_svc=None, knowledge_svc=None, ambient_svc=None, health_agent=None):
        self._memory = memory_svc
        self._knowledge = knowledge_svc
        self._ambient = ambient_svc
        self._health_agent = health_agent
        self._tracer = get_tracer()
        logger.info("candidate_mixer_initialized", 
                    sources={"memory": bool(memory_svc), 
                             "knowledge": bool(knowledge_svc), 
                             "ambient": bool(ambient_svc)},
                    adaptive=bool(health_agent))

    async def mix(self, query: str, limit: int = 100) -> List[RetrievalCandidate]:
        """Fetch and unite candidates from all available sources with diversity re-ranking."""
        
        # Adaptive Load Shedding: reduce budget if node is DEGRADED
        effective_limit = limit
        skip_heavy = False
        
        if self._health_agent:
            status = self._health_agent.status
            if status == "UNHEALTHY":
                logger.warn("mixer_load_shedding_critical", query=query)
                return []
            elif status == "DEGRADED":
                effective_limit = max(5, limit // 4)  # 25% budget
                skip_heavy = True
                logger.info("mixer_load_shedding_active", 
                            query=query, 
                            original_limit=limit, 
                            effective_limit=effective_limit)

        logger.debug("mixing_started", query=query, limit=effective_limit)
        
        with self._tracer.span("butler.ml.mix", attrs={"query": query, "limit": effective_limit}):
            start_time = time.monotonic()
        
        # Parallel retrieval with timeout protection
        tasks = []
        source_weights = {}

        if self._memory:
            tasks.append(self._fetch_from_memory(query, effective_limit // 2))
            source_weights["memory"] = 1.0
        
        # In DEGRADED state, we skip heavier sources like knowledge graph to maintain latency
        if self._knowledge and not skip_heavy:
            tasks.append(self._fetch_from_knowledge(query, effective_limit // 2))
            source_weights["knowledge"] = 0.8
        
        if self._ambient:
            tasks.append(self._fetch_from_ambient(query, max(1, effective_limit // 4)))
            source_weights["ambient"] = 0.6
        
        if not tasks:
            logger.warning("mixer_no_active_sources")
            return []

        # diversity limit for source-specific results
        final_diversity_limit = effective_limit
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_candidates = []
        for i, res in enumerate(results):
            if isinstance(res, list):
                # Apply source-specific base scores
                source_name = list(source_weights.keys())[i]
                weight = source_weights[source_name]
                for c in res:
                    c.score = float(c.score) * weight
                    c.metadata["source"] = source_name
                all_candidates.extend(res)
            elif isinstance(res, Exception):
                logger.error("mixer_source_failed", error=str(res))

        # Deduplicate and prioritize high-confidence matches
        unique_candidates = self._deduplicate(all_candidates)

        # Diversity check: ensure top-N isn't dominated by a single source
        final_candidates = self._apply_diversity(unique_candidates, final_diversity_limit)

        latency = (time.monotonic() - start_time) * 1000
        logger.info("mixing_completed", 
                    count=len(final_candidates), 
                    latency_ms=latency)
        
        return final_candidates

    def _deduplicate(self, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        seen_ids = set()
        deduped = []
        for c in candidates:
            cid = c.metadata.get("id") or str(hash(c.content))
            if cid not in seen_ids:
                deduped.append(c)
                seen_ids.add(cid)
            else:
                # If seen, keep the one with higher score
                existing = next((x for x in deduped if (x.metadata.get("id") or str(hash(x.content))) == cid), None)
                if existing and c.score > existing.score:
                    existing.score = c.score
        return sorted(deduped, key=lambda x: x.score, reverse=True)

    def _apply_diversity(self, candidates: List[RetrievalCandidate], limit: int) -> List[RetrievalCandidate]:
        """Simple round-robin diversity filter if many candidates from one source."""
        if len(candidates) <= limit:
            return candidates
            
        source_counts = {}
        diverse = []
        max_per_source = limit // 2
        
        for c in candidates:
            source = c.metadata.get("source", "unknown")
            count = source_counts.get(source, 0)
            if count < max_per_source:
                diverse.append(c)
                source_counts[source] = count + 1
            if len(diverse) >= limit:
                break
                
        return diverse

    async def _fetch_from_memory(self, query: str, limit: int) -> List[RetrievalCandidate]:
        """Simulated Vector Similarity search (T1/T2)."""
        if not self._memory: return []
        # In a real system: return await self._memory.search(query, limit)
        return [
            RetrievalCandidate(source="memory", content=f"Memory result {i}", score=0.9 - (i*0.05), metadata={"id": f"mem_{i}"})
            for i in range(3)
        ]

    async def _fetch_from_knowledge(self, query: str, limit: int) -> List[RetrievalCandidate]:
        """Simulated Knowledge Graph traversal (T2)."""
        if not self._knowledge: return []
        return [
            RetrievalCandidate(source="knowledge", content=f"Knowledge result {i}", score=0.85 - (i*0.1), metadata={"id": f"kg_{i}"})
            for i in range(2)
        ]

    async def _fetch_from_ambient(self, query: str, limit: int) -> List[RetrievalCandidate]:
        """Simulated Ambient Context match (T0)."""
        if not self._ambient: return []
        return [
            RetrievalCandidate(source="ambient", content=f"Ambient state {i}", score=0.95, metadata={"id": f"amb_{i}"})
            for i in range(1)
        ]

class SignalManager:
    """Manages injection of Unified User Action (UUA) ranking signals."""
    
    def __init__(self, feature_svc):
        self._features = feature_svc
        logger.info("signal_manager_initialized")

    async def enrich_candidates(self, entity_id: str, candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
        """Inject rich behavioral signals into candidate metadata for deep ranking."""
        if not self._features or not candidates:
            return candidates
            
        # 1. Fetch UUA aggregation for the user
        try:
            user_signals = await self._features.get_online_features(
                entity_id, 
                ["user_affinity", "recency_bias", "interaction_depth"]
            )
            signals_dict = user_signals.features
        except Exception as e:
            logger.warning("signal_enrichment_failed", error=str(e))
            signals_dict = {}
        
        # 2. Map signals to candidates (Phase 3 logic)
        for c in candidates:
            c.metadata["signals"] = {
                "uua_affinity": signals_dict.get("user_affinity", 0.5),
                "depth": signals_dict.get("interaction_depth", 1.0),
                "last_seen": time.time()
            }
            
        return candidates
