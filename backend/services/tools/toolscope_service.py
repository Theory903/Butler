"""ToolScope Service - Semantic Tool Retrieval for Butler.

4-Stage Tool Retrieval Pipeline:
- Stage 1: Semantic Retrieval (EmbeddingService-backed)
- Stage 2: Policy Filtering (hard filter)
- Stage 3: Reranking (cross-encoder + metadata)
- Stage 4: Dynamic Cutoff (threshold-based)

This replaces simple tool counting with RAG-based tool selection, dramatically
improving accuracy and reducing prompt bloat as toolsets scale.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

from domain.tools.selection_contract import (
    ToolRejection,
    ToolSelection,
    ToolSelectionContract,
)
from domain.tools.specs import ButlerToolSpec
from services.intent.intent_builder import IntentContext

logger = structlog.get_logger(__name__)


class ButlerEmbedderAdapter:
    """Adapter for ToolScope using Butler's existing EmbeddingService.

    Wraps Butler's EmbeddingService to provide the synchronous embed_texts
    interface expected by ToolScope.
    """

    def __init__(self, embedding_service: Any):
        """Initialize embedder adapter with Butler's EmbeddingService.

        Args:
            embedding_service: Butler EmbeddingService instance.
        """
        self._embedding_service = embedding_service

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts synchronously.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (list of floats).
        """
        import asyncio

        # Butler's EmbeddingService is async, so we need to run it in an event loop
        # This is safe to call from sync context in ToolScope initialization
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        embeddings = loop.run_until_complete(
            self._embedding_service.embed_batch(texts)
        )
        return embeddings


class ToolScopeService:
    """Service for semantic tool retrieval using ToolScope.

    4-Stage Retrieval Pipeline:
    - Stage 1: Semantic Retrieval (EmbeddingService-backed)
    - Stage 2: Policy Filtering (hard filter)
    - Stage 3: Reranking (cross-encoder + metadata)
    - Stage 4: Dynamic Cutoff (threshold-based)

    Manages ToolScope index lifecycle and provides filtering API
    with observability and Butler-specific policy integration.
    """

    def __init__(
        self,
        embedding_adapter: ButlerEmbedderAdapter,
        k: int = 8,
        enable_reranking: bool = False,
        enable_sticky_sessions: bool = True,
        max_risk_tier: str = "L2",
        tool_text_truncate: int = 256,
        dynamic_cutoff_enabled: bool = True,
        cutoff_threshold: float = 0.5,
        max_tools: int = 12,
        reranking_blend_semantic: float = 0.6,
        reranking_blend_intent: float = 0.2,
        reranking_blend_success: float = 0.1,
        reranking_blend_cost: float = 0.1,
    ):
        """Initialize ToolScope service.

        Args:
            embedding_adapter: ButlerEmbedderAdapter wrapping EmbeddingService.
            k: Number of tools to retrieve per query (base retrieval).
            enable_reranking: Enable cross-encoder reranking for better precision.
            enable_sticky_sessions: Enable sticky sessions for multi-turn conversations.
            max_risk_tier: Maximum risk tier to allow by default.
            tool_text_truncate: Truncate tool descriptions to this length.
            dynamic_cutoff_enabled: Enable dynamic threshold-based cutoff.
            cutoff_threshold: Minimum score threshold for tool selection.
            max_tools: Maximum number of tools to return after cutoff.
            reranking_blend_semantic: Weight for semantic score in reranking.
            reranking_blend_intent: Weight for intent match in reranking.
            reranking_blend_success: Weight for tool success rate in reranking.
            reranking_blend_cost: Weight for cost bias in reranking.
        """
        self._embedding_adapter = embedding_adapter
        self._k = k
        self._enable_reranking = enable_reranking
        self._enable_sticky_sessions = enable_sticky_sessions
        self._max_risk_tier = max_risk_tier
        self._tool_text_truncate = tool_text_truncate
        self._dynamic_cutoff_enabled = dynamic_cutoff_enabled
        self._cutoff_threshold = cutoff_threshold
        self._max_tools = max_tools
        self._reranking_blend_semantic = reranking_blend_semantic
        self._reranking_blend_intent = reranking_blend_intent
        self._reranking_blend_success = reranking_blend_success
        self._reranking_blend_cost = reranking_blend_cost
        self._index = None
        self._toolscope = None
        self._load_toolscope()

    def _load_toolscope(self) -> None:
        """Import ToolScope library."""
        try:
            import toolscope

            self._toolscope = toolscope
            logger.info("toolscope_loaded")
        except ImportError:
            logger.error("toolscope_not_installed")
            raise ImportError(
                "ToolScope not installed. Add 'toolscope>=0.1.0' to requirements.txt"
            )

    def _convert_butler_spec_to_toolscope(self, spec: ButlerToolSpec) -> dict[str, Any]:
        """Convert Butler tool spec to ToolScope canonical format.

        Args:
            spec: Butler tool specification.

        Returns:
            ToolScope-compatible tool dictionary.
        """
        return {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.input_schema,
            # Preserve original Butler spec for reference
            "_butler_spec": spec,
            # Add tags from Butler for filtering
            "tags": list(spec.tags) + [spec.risk_tier.value, spec.owner],
        }

    def build_index(self, tools: list[ButlerToolSpec]) -> None:
        """Build ToolScope index from Butler tool specs.

        Args:
            tools: List of Butler tool specifications.
        """
        if self._toolscope is None:
            raise RuntimeError("ToolScope not loaded")

        # Convert Butler specs to ToolScope format
        toolscope_tools = [
            self._convert_butler_spec_to_toolscope(spec) for spec in tools
        ]

        # Configure ToolScope
        embedding_config = self._toolscope.EmbeddingConfig(
            provider="custom",
            model="butler-embeddings",
            allow_download=False,
        )

        tool_text_config = self._toolscope.ToolTextConfig(
            use_name=True,
            use_description=True,
            use_schema=False,  # Schema can be verbose, focus on name+description
            truncate=self._tool_text_truncate,
        )

        # Configure sticky sessions if enabled
        sticky_config = None
        if self._enable_sticky_sessions:
            sticky_config = self._toolscope.StickySessionConfig(
                enabled=True,
                similarity_threshold_reuse=0.95,
                similarity_threshold_refresh=0.8,
                sticky_keep=2,
            )

        # Configure reranking if enabled
        reranking_config = None
        if self._enable_reranking:
            reranking_config = self._toolscope.RerankingConfig(
                model="cross-encoder/ms-marco-MiniLM-L-6-v2",
                pool_size=20,
            )

        # Build index
        try:
            self._index = self._toolscope.index(
                tools=toolscope_tools,
                embedder=self._embedding_adapter,
                embedding=embedding_config,
                tool_text=tool_text_config,
                sticky_session=sticky_config,
                reranking=reranking_config,
            )
            logger.info(
                "toolscope_index_built",
                tool_count=len(tools),
                k=self._k,
                reranking=self._enable_reranking,
                sticky_sessions=self._enable_sticky_sessions,
            )
        except Exception as e:
            logger.error("toolscope_index_build_failed", error=str(e))
            raise

    def retrieve(
        self,
        intent_context: IntentContext,
        allow_tags: list[str] | None = None,
        deny_tags: list[str] | None = None,
        account_permissions: frozenset[str] | None = None,
        max_risk_tier: str | None = None,
        tool_success_rates: dict[str, float] | None = None,
    ) -> ToolSelectionContract:
        """Retrieve tools using 4-stage pipeline.

        Stage 1: Semantic Retrieval (EmbeddingService-backed)
        Stage 2: Policy Filtering (hard filter)
        Stage 3: Reranking (cross-encoder + metadata)
        Stage 4: Dynamic Cutoff (threshold-based)

        Args:
            intent_context: Intent context from IntentBuilder.
            allow_tags: Optional list of tags to allow (whitelist).
            deny_tags: Optional list of tags to deny (blacklist).
            account_permissions: Account permissions for policy filtering.
            max_risk_tier: Maximum risk tier to allow (e.g., "L2").
            tool_success_rates: Optional tool success rates for reranking.

        Returns:
            ToolSelectionContract with selected and rejected tools.
        """
        if self._index is None:
            logger.warning("toolscope_index_not_built_returning_empty")
            return ToolSelectionContract(
                selected_tools=[],
                rejected_tools=[],
                retrieval_metadata={"error": "index_not_built"},
                intent_context={"query": intent_context.query},
            )

        # Use instance default if not specified
        effective_max_risk_tier = max_risk_tier or self._max_risk_tier

        try:
            # Stage 1: Semantic Retrieval (broad recall)
            candidates, stage1_trace = self._stage1_semantic_retrieval(
                intent_context.query, allow_tags, deny_tags
            )

            # Stage 2: Policy Filtering (hard filter)
            policy_filtered, stage2_trace = self._stage2_policy_filter(
                candidates,
                effective_max_risk_tier,
                account_permissions,
            )

            # Stage 3: Reranking (if enabled)
            if self._enable_reranking:
                ranked_tools, stage3_trace = self._stage3_rerank(
                    policy_filtered,
                    intent_context,
                    tool_success_rates,
                )
            else:
                ranked_tools = policy_filtered
                stage3_trace = {"reranking_disabled": True}

            # Stage 4: Dynamic Cutoff
            selected_tools, cutoff_rejected, stage4_trace = self._stage4_dynamic_cutoff(
                ranked_tools
            )

            # Build selection contract
            selected = [
                ToolSelection(
                    name=tool["name"],
                    reason=self._generate_selection_reason(tool, intent_context),
                    confidence=tool.get("final_score", 0.0),
                    score_components=tool.get("score_components", {}),
                    spec=tool.get("_butler_spec"),
                )
                for tool in selected_tools
            ]

            rejected = [
                ToolRejection(
                    name=tool["name"],
                    reason=tool.get("rejection_reason", "unknown"),
                    stage=tool.get("rejection_stage", "unknown"),
                    score=tool.get("score"),
                    spec=tool.get("_butler_spec"),
                )
                for tool in cutoff_rejected
            ]

            # Combine with policy rejections
            for tool_rejection in stage2_trace.get("policy_filtered", []):
                rejected.append(
                    ToolRejection(
                        name=tool_rejection["tool"],
                        reason=tool_rejection["reason"],
                        stage="policy",
                        score=None,
                        spec=None,
                    )
                )

            retrieval_metadata = {
                "stage1_candidates": stage1_trace.get("candidate_count", 0),
                "stage2_policy_filtered": len(stage2_trace.get("policy_filtered", [])),
                "stage2_passed": len(policy_filtered),
                "stage3_reranking_enabled": self._enable_reranking,
                "stage4_cutoff_enabled": self._dynamic_cutoff_enabled,
                "stage4_cutoff_threshold": self._cutoff_threshold if self._dynamic_cutoff_enabled else None,
                "final_selected": len(selected),
                "final_rejected": len(rejected),
                "intent_type": intent_context.intent_type,
                "risk_level": intent_context.constraints.risk_level,
            }

            logger.info(
                "toolscope_retrieval_complete",
                **retrieval_metadata,
            )

            return ToolSelectionContract(
                selected_tools=selected,
                rejected_tools=rejected,
                retrieval_metadata=retrieval_metadata,
                intent_context={"query": intent_context.query, "type": intent_context.intent_type},
            )

        except Exception as e:
            logger.error("toolscope_retrieval_failed", error=str(e))
            return ToolSelectionContract(
                selected_tools=[],
                rejected_tools=[],
                retrieval_metadata={"error": str(e)},
                intent_context={"query": intent_context.query},
            )

    def _stage1_semantic_retrieval(
        self,
        query: str,
        allow_tags: list[str] | None,
        deny_tags: list[str] | None,
    ) -> tuple[list[dict], dict]:
        """Stage 1: Semantic retrieval using EmbeddingService.

        Args:
            query: Normalized query string.
            allow_tags: Optional allow tags.
            deny_tags: Optional deny tags.

        Returns:
            Tuple of (candidate tools, trace metadata).
        """
        # Retrieve more candidates for policy filtering
        retrieval_k = self._k * 3

        candidates, trace = self._index.filter_with_trace(
            messages=query,
            k=retrieval_k,
            allow_tags=allow_tags,
            deny_tags=deny_tags,
        )

        trace["candidate_count"] = len(candidates)
        return candidates, trace

    def _stage2_policy_filter(
        self,
        candidates: list[dict],
        max_risk_tier: str,
        account_permissions: frozenset[str] | None,
    ) -> tuple[list[dict], dict]:
        """Stage 2: Policy filtering (hard filter).

        Args:
            candidates: Candidate tools from Stage 1.
            max_risk_tier: Maximum risk tier.
            account_permissions: Account permissions.

        Returns:
            Tuple of (filtered tools, trace metadata).
        """
        filtered = []
        policy_filtered = []
        risk_order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}

        for tool in candidates:
            butler_spec = tool.get("_butler_spec")
            if not butler_spec:
                continue

            # Check risk tier
            if risk_order.get(butler_spec.risk_tier.value, 99) > risk_order.get(
                max_risk_tier, 99
            ):
                policy_filtered.append({
                    "tool": butler_spec.name,
                    "reason": "risk_tier_exceeded",
                    "tier": butler_spec.risk_tier.value,
                })
                continue

            # Check permissions
            if account_permissions and not butler_spec.required_permissions.issubset(
                account_permissions
            ):
                policy_filtered.append({
                    "tool": butler_spec.name,
                    "reason": "insufficient_permissions",
                    "required": list(butler_spec.required_permissions),
                })
                continue

            # Check if enabled
            if not butler_spec.enabled:
                policy_filtered.append({
                    "tool": butler_spec.name,
                    "reason": "tool_disabled",
                })
                continue

            # Preserve original score
            tool["semantic_score"] = tool.get("score", 0.0)
            filtered.append(tool)

        trace = {
            "policy_filtered": policy_filtered,
            "passed_count": len(filtered),
        }

        return filtered, trace

    def _stage3_rerank(
        self,
        tools: list[dict],
        intent_context: IntentContext,
        tool_success_rates: dict[str, float] | None,
    ) -> tuple[list[dict], dict]:
        """Stage 3: Reranking with metadata boost.

        Args:
            tools: Tools from Stage 2.
            intent_context: Intent context for intent matching.
            tool_success_rates: Tool success rates for boosting.

        Returns:
            Tuple of (reranked tools, trace metadata).
        """
        reranked = []

        for tool in tools:
            butler_spec = tool.get("_butler_spec")
            if not butler_spec:
                continue

            semantic_score = tool.get("semantic_score", 0.0)

            # Intent match score (simple keyword overlap for now)
            intent_match_score = self._calculate_intent_match(
                tool, intent_context
            )

            # Success rate boost
            success_rate = tool_success_rates.get(butler_spec.name, 0.5) if tool_success_rates else 0.5

            # Cost bias (lower cost preferred if cost_sensitive)
            cost_bias = 0.5  # Neutral default
            if intent_context.constraints.cost_sensitive:
                # Prefer lower risk tools as proxy for cost
                risk_order = {"L0": 1.0, "L1": 0.8, "L2": 0.5, "L3": 0.2, "L4": 0.0}
                cost_bias = risk_order.get(butler_spec.risk_tier.value, 0.5)

            # Blend scores
            final_score = (
                self._reranking_blend_semantic * semantic_score
                + self._reranking_blend_intent * intent_match_score
                + self._reranking_blend_success * success_rate
                + self._reranking_blend_cost * cost_bias
            )

            tool["final_score"] = final_score
            tool["score_components"] = {
                "semantic": semantic_score,
                "intent": intent_match_score,
                "success": success_rate,
                "cost": cost_bias,
            }

            reranked.append(tool)

        # Sort by final score
        reranked.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)

        trace = {
            "reranking_applied": True,
            "blend_weights": {
                "semantic": self._reranking_blend_semantic,
                "intent": self._reranking_blend_intent,
                "success": self._reranking_blend_success,
                "cost": self._reranking_blend_cost,
            },
        }

        return reranked, trace

    def _calculate_intent_match(
        self, tool: dict, intent_context: IntentContext
    ) -> float:
        """Calculate intent match score for a tool.

        Args:
            tool: Tool dictionary.
            intent_context: Intent context.

        Returns:
            Intent match score (0.0 to 1.0).
        """
        butler_spec = tool.get("_butler_spec")
        if not butler_spec:
            return 0.0

        # Simple keyword overlap between query and tool description/tags
        query_words = set(intent_context.query.lower().split())
        description_words = set(butler_spec.description.lower().split())
        tag_words = set(tag.lower() for tag in butler_spec.tags)

        overlap = len(query_words & (description_words | tag_words))
        total = len(query_words)

        if total == 0:
            return 0.0

        return min(overlap / total, 1.0)

    def _stage4_dynamic_cutoff(
        self, tools: list[dict]
    ) -> tuple[list[dict], list[dict], dict]:
        """Stage 4: Dynamic cutoff based on threshold.

        Args:
            tools: Tools from Stage 3.

        Returns:
            Tuple of (selected tools, rejected tools, trace metadata).
        """
        if not self._dynamic_cutoff_enabled:
            # Fixed K fallback
            selected = tools[: self._max_tools]
            rejected = tools[self._max_tools :]
            trace = {
                "cutoff_mode": "fixed_k",
                "cutoff_threshold": None,
            }
            return selected, rejected, trace

        selected = []
        rejected = []

        for tool in tools:
            score = tool.get("final_score", 0.0)
            if score >= self._cutoff_threshold and len(selected) < self._max_tools:
                selected.append(tool)
            else:
                tool["rejection_reason"] = f"score_below_threshold: {score:.3f}"
                tool["rejection_stage"] = "cutoff"
                tool["score"] = score
                rejected.append(tool)

        trace = {
            "cutoff_mode": "dynamic_threshold",
            "cutoff_threshold": self._cutoff_threshold,
            "selected_above_threshold": len(selected),
            "rejected_below_threshold": len(rejected),
        }

        return selected, rejected, trace

    def _generate_selection_reason(
        self, tool: dict, intent_context: IntentContext
    ) -> str:
        """Generate reason for tool selection.

        Args:
            tool: Selected tool dictionary.
            intent_context: Intent context.

        Returns:
            Human-readable selection reason.
        """
        butler_spec = tool.get("_butler_spec")
        if not butler_spec:
            return "Tool matched query"

        score_components = tool.get("score_components", {})
        semantic_score = score_components.get("semantic", 0.0)
        intent_match = score_components.get("intent", 0.0)

        reasons = []
        if semantic_score > 0.7:
            reasons.append("high semantic similarity")
        if intent_match > 0.5:
            reasons.append("matches user intent")

        if reasons:
            return f"Selected because: {', '.join(reasons)}"
        return f"Selected based on overall score ({tool.get('final_score', 0.0):.2f})"

    def refresh_index(self, tools: list[ButlerToolSpec]) -> None:
        """Refresh the ToolScope index with updated tools.

        Args:
            tools: Updated list of Butler tool specifications.
        """
        logger.info("toolscope_index_refresh")
        self.build_index(tools)


# Singleton instance
_toolscope_service: ToolScopeService | None = None


def get_toolscope_service(
    embedding_service: Any,
    k: int = 8,
    enable_reranking: bool = False,
    enable_sticky_sessions: bool = True,
    max_risk_tier: str = "L2",
    tool_text_truncate: int = 256,
    dynamic_cutoff_enabled: bool = True,
    cutoff_threshold: float = 0.5,
    max_tools: int = 12,
    reranking_blend_semantic: float = 0.6,
    reranking_blend_intent: float = 0.2,
    reranking_blend_success: float = 0.1,
    reranking_blend_cost: float = 0.1,
) -> ToolScopeService:
    """Get the singleton ToolScope service instance.

    Args:
        embedding_service: Butler EmbeddingService instance.
        k: Number of tools to retrieve per query (base retrieval).
        enable_reranking: Enable cross-encoder reranking.
        enable_sticky_sessions: Enable sticky sessions for multi-turn.
        max_risk_tier: Maximum risk tier to allow by default.
        tool_text_truncate: Truncate tool descriptions to this length.
        dynamic_cutoff_enabled: Enable dynamic threshold-based cutoff.
        cutoff_threshold: Minimum score threshold for tool selection.
        max_tools: Maximum number of tools to return after cutoff.
        reranking_blend_semantic: Weight for semantic score in reranking.
        reranking_blend_intent: Weight for intent match in reranking.
        reranking_blend_success: Weight for tool success rate in reranking.
        reranking_blend_cost: Weight for cost bias in reranking.

    Returns:
        ToolScope service instance.
    """
    global _toolscope_service
    if _toolscope_service is None:
        embedding_adapter = ButlerEmbedderAdapter(embedding_service)
        _toolscope_service = ToolScopeService(
            embedding_adapter=embedding_adapter,
            k=k,
            enable_reranking=enable_reranking,
            enable_sticky_sessions=enable_sticky_sessions,
            max_risk_tier=max_risk_tier,
            tool_text_truncate=tool_text_truncate,
            dynamic_cutoff_enabled=dynamic_cutoff_enabled,
            cutoff_threshold=cutoff_threshold,
            max_tools=max_tools,
            reranking_blend_semantic=reranking_blend_semantic,
            reranking_blend_intent=reranking_blend_intent,
            reranking_blend_success=reranking_blend_success,
            reranking_blend_cost=reranking_blend_cost,
        )
    return _toolscope_service
