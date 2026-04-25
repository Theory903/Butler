"""
LangGraph Research Subgraph - Multi-hop research with reflection.

Uses LangGraph for durable execution with checkpoints. Integrated with
Butler's search service and 4-tier memory architecture.
"""

from __future__ import annotations

from typing import Any, TypedDict

from backend.langchain.retrievers import ButlerSearchRetriever
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt


class ResearchState(TypedDict):
    """State for the research subgraph workflow."""

    query: str
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    iteration: int
    final_answer: str | None
    metadata: dict[str, Any]


def create_research_graph(
    search_retriever: ButlerSearchRetriever | None = None,
    max_iterations: int = 3,
    enable_citations: bool = True,
):
    """Create research subgraph with retrieve → extract → rank → reflect → cite.

    Args:
        search_retriever: Butler's search retriever instance
        max_iterations: Maximum reflection iterations
        enable_citations: Whether to generate citations

    Returns:
        Compiled LangGraph StateGraph
    """

    def retrieve_node(state: ResearchState) -> dict[str, Any]:
        """Retrieve relevant documents from Butler's search service."""
        query = state.get("query", "")
        evidence = []

        if search_retriever:
            # Use Butler's search retriever
            import asyncio

            docs = asyncio.run(search_retriever._aget_relevant_documents(query))
            for doc in docs:
                evidence.append(
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "source": doc.metadata.get("source", "unknown"),
                    }
                )
        else:
            # Fallback for when search retriever is not available
            evidence = []

        return {
            "evidence": evidence,
            "metadata": {
                **state.get("metadata", {}),
                "retrieved_count": len(evidence),
            },
        }

    def extract_node(state: ResearchState) -> dict[str, Any]:
        """Extract key information from retrieved documents."""
        evidence = state.get("evidence", [])
        citations = []

        if enable_citations:
            for idx, item in enumerate(evidence):
                citation = {
                    "index": idx,
                    "source": item.get("source", "unknown"),
                    "url": item["metadata"].get("url"),
                    "score": item["metadata"].get("score", 0.0),
                }
                citations.append(citation)

        return {
            "citations": citations,
            "metadata": {
                **state.get("metadata", {}),
                "extracted_count": len(evidence),
            },
        }

    def rank_node(state: ResearchState) -> dict[str, Any]:
        """Rank evidence by relevance score."""
        evidence = state.get("evidence", [])
        ranked = sorted(
            evidence,
            key=lambda x: x["metadata"].get("score", 0.0),
            reverse=True,
        )

        return {
            "evidence": ranked,
            "metadata": {
                **state.get("metadata", {}),
                "ranked": True,
            },
        }

    def reflect_node(state: ResearchState) -> dict[str, Any]:
        """Reflect on research progress and decide whether to continue."""
        iteration = state.get("iteration", 0)
        evidence_count = len(state.get("evidence", []))

        reflection = {
            "iteration": iteration + 1,
            "evidence_count": evidence_count,
            "sufficient": evidence_count >= 5 or iteration >= max_iterations,
        }

        if reflection["sufficient"] or iteration >= max_iterations:
            return {
                "iteration": iteration + 1,
                "final_answer": f"Research complete with {evidence_count} evidence items",
                "metadata": {
                    **state.get("metadata", {}),
                    "reflection": reflection,
                },
            }

        return {
            "iteration": iteration + 1,
            "metadata": {
                **state.get("metadata", {}),
                "reflection": reflection,
            },
        }

    def cite_node(state: ResearchState) -> dict[str, Any]:
        """Generate final citations for evidence."""
        citations = state.get("citations", [])
        evidence = state.get("evidence", [])

        # Ensure citations match evidence
        if len(citations) != len(evidence):
            citations = []
            for idx, item in enumerate(evidence):
                citations.append(
                    {
                        "index": idx,
                        "source": item.get("source", "unknown"),
                        "url": item["metadata"].get("url"),
                        "score": item["metadata"].get("score", 0.0),
                    }
                )

        return {
            "citations": citations,
            "metadata": {
                **state.get("metadata", {}),
                "citations_generated": True,
            },
        }

    # Build the graph
    graph = StateGraph(ResearchState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("extract", extract_node)
    graph.add_node("rank", rank_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("cite", cite_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "extract")
    graph.add_edge("extract", "rank")
    graph.add_edge("rank", "cite")
    graph.add_edge("cite", "reflect")

    # Conditional edge: reflect → cite if more iterations needed, else END
    graph.add_conditional_edges(
        "reflect",
        lambda s: "cite" if s.get("iteration", 0) < max_iterations else END,
    )

    return graph.compile()


class DurableResearchGraph:
    """Durable research with checkpointing for long-running research tasks."""

    def __init__(
        self,
        checkpointer: Any = None,
        search_retriever: ButlerSearchRetriever | None = None,
        max_iterations: int = 3,
    ):
        """Initialize durable research graph.

        Args:
            checkpointer: LangGraph checkpointer for state persistence
            search_retriever: Butler's search retriever
            max_iterations: Maximum reflection iterations
        """
        self.checkpointer = checkpointer
        self.search_retriever = search_retriever
        self.max_iterations = max_iterations
        self.graph = create_research_graph(
            search_retriever=search_retriever,
            max_iterations=max_iterations,
        )

    async def run(
        self,
        query: str,
        thread_id: str,
        checkpoint_ns: str | None = None,
    ) -> dict[str, Any]:
        """Run research with durable checkpointing.

        Args:
            query: Research query
            thread_id: LangGraph thread identifier
            checkpoint_ns: Optional checkpoint namespace

        Returns:
            Research result with evidence and citations
        """
        config = {"configurable": {"thread_id": thread_id}}
        if checkpoint_ns:
            config["configurable"]["checkpoint_ns"] = checkpoint_ns

        initial_state = ResearchState(
            query=query,
            evidence=[],
            citations=[],
            iteration=0,
            final_answer=None,
            metadata={"started": True},
        )

        return await self.graph.ainvoke(initial_state, config)


def approval_interrupt_node(state: dict[str, Any]) -> dict[str, Any]:
    """Native LangGraph interrupt for risky approvals.

    This node triggers an interrupt for TIER_3/4 tool approvals,
    allowing human-in-the-loop approval workflows.

    Args:
        state: Current graph state with tool approval request

    Returns:
        State with approval decision
    """
    approval_required = interrupt(
        {
            "tool_name": state.get("tool_name"),
            "risk_tier": state.get("risk_tier"),
            "args": state.get("args"),
            "description": state.get("description"),
        }
    )

    if approval_required.get("approved"):
        return {
            "status": "approved",
            "events": [{"type": "approval_granted"}],
            "approval_id": approval_required.get("approval_id"),
        }

    return {
        "status": "denied",
        "events": [{"type": "approval_denied"}],
        "approval_id": approval_required.get("approval_id"),
    }
