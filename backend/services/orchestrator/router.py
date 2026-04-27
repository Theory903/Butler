"""Intent + Capability Router for Butler production runtime.

Classifies what kind of execution is needed for a request.
Not everything needs an LLM. Not everything needs LangGraph.
Not everything needs 39 tools.

Routing examples:
- "what is the time" → deterministic_tool
- "where am I" → deterministic_tool or permission response
- "summarize my uploaded docs" → llm_answer + RAG
- "what do we know about project X" → llm_answer + hybrid RAG/KAG
- "send this email" → human_approval_workflow
- "research this topic deeply" → async_job or durable_workflow
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from domain.context.local_resolver import LocalContextResolver
from domain.runtime.execution_class import ExecutionClass, RetrievalMode


class IntentResult(BaseModel):
    """Result of intent classification."""

    intent: str
    confidence: float
    requires_llm: bool
    requires_tools: bool
    required_capabilities: list[str] = Field(default_factory=list)
    execution_class: ExecutionClass
    retrieval_required: bool = False
    retrieval_mode: RetrievalMode | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentRouter:
    """Classify execution requirements for requests.

    Rules:
    - Not every task gets LLM
    - Not every task gets LangGraph
    - Not every task gets 39 tools
    - Do not turn "what time is it" into a distributed systems tragedy
    """

    def __init__(self) -> None:
        self._local_resolver = LocalContextResolver()

    def set_local_context(self, timezone: str | None = None, locale: str | None = None) -> None:
        """Set local context for deterministic resolution."""
        if timezone:
            self._local_resolver.set_timezone(timezone)
        if locale:
            self._local_resolver.set_locale(locale)

    def classify(self, query: str, context: dict[str, Any] | None = None) -> IntentResult:
        """Classify intent and determine execution class."""
        context = context or {}
        query_lower = query.lower().strip()

        # First check if local resolver can answer deterministically
        if self._local_resolver.can_answer(query):
            local_answer = self._local_resolver.resolve(query)
            return IntentResult(
                intent=local_answer.intent,
                confidence=local_answer.confidence,
                requires_llm=local_answer.requires_llm,
                requires_tools=False,
                required_capabilities=[],
                execution_class=ExecutionClass.DETERMINISTIC_TOOL,
                retrieval_required=False,
                metadata={"local_answer": local_answer.answer},
            )

        # Check for RAG/KAG retrieval needs
        retrieval_mode = self._classify_retrieval_need(query, context)
        if retrieval_mode != RetrievalMode.NONE:
            return IntentResult(
                intent="retrieval_query",
                confidence=0.8,
                requires_llm=True,
                requires_tools=True,
                required_capabilities=["rag", "kag"],
                execution_class=ExecutionClass.LLM_WITH_TOOLS,
                retrieval_required=True,
                retrieval_mode=retrieval_mode,
            )

        # Check for approval-required actions
        if self._requires_approval(query):
            return IntentResult(
                intent="approval_required_action",
                confidence=0.9,
                requires_llm=False,
                requires_tools=True,
                required_capabilities=["approval", "sandbox"],
                execution_class=ExecutionClass.HUMAN_APPROVAL_WORKFLOW,
                retrieval_required=False,
            )

        # Check for long-running async tasks
        if self._requires_async_job(query):
            return IntentResult(
                intent="async_job",
                confidence=0.8,
                requires_llm=False,
                requires_tools=True,
                required_capabilities=["async", "queue"],
                execution_class=ExecutionClass.ASYNC_JOB,
                retrieval_required=False,
            )

        # Check for durable workflow needs
        if self._requires_durable_workflow(query):
            return IntentResult(
                intent="durable_workflow",
                confidence=0.8,
                requires_llm=True,
                requires_tools=True,
                required_capabilities=["checkpoint", "resume"],
                execution_class=ExecutionClass.DURABLE_WORKFLOW,
                retrieval_required=False,
            )

        # Default to LLM answer for general conversation
        return IntentResult(
            intent="general_conversation",
            confidence=0.7,
            requires_llm=True,
            requires_tools=False,
            required_capabilities=[],
            execution_class=ExecutionClass.LLM_ANSWER,
            retrieval_required=False,
        )

    def _classify_retrieval_need(self, query: str, context: dict[str, Any]) -> RetrievalMode:
        """Classify if RAG/KAG retrieval is needed."""
        query_lower = query.lower()

        # Keywords suggesting document/session retrieval
        rag_keywords = [
            "summarize my",
            "what did i say",
            "what did i decide",
            "my notes",
            "my documents",
            "uploaded files",
            "previous conversation",
            "session history",
        ]

        # Keywords suggesting entity/relationship queries
        kag_keywords = [
            "what do we know about",
            "project",
            "entity",
            "relationship",
            "graph",
            "knowledge",
            "facts about",
        ]

        has_rag = any(kw in query_lower for kw in rag_keywords)
        has_kag = any(kw in query_lower for kw in kag_keywords)

        if has_rag and has_kag:
            return RetrievalMode.HYBRID
        if has_rag:
            return RetrievalMode.RAG
        if has_kag:
            return RetrievalMode.KAG

        return RetrievalMode.NONE

    def _requires_approval(self, query: str) -> bool:
        """Check if query requires approval (L2/L3 actions)."""
        query_lower = query.lower()

        approval_keywords = [
            "send email",
            "send message",
            "write file",
            "delete file",
            "run terminal",
            "execute command",
            "browser automation",
            "login",
            "purchase",
            "transfer",
        ]

        return any(kw in query_lower for kw in approval_keywords)

    def _requires_async_job(self, query: str) -> bool:
        """Check if query requires async job execution."""
        query_lower = query.lower()

        async_keywords = [
            "index all",
            "scrape website",
            "process all files",
            "bulk",
            "batch",
            "long research",
            "deep analysis",
        ]

        return any(kw in query_lower for kw in async_keywords)

    def _requires_durable_workflow(self, query: str) -> bool:
        """Check if query requires durable workflow with checkpointing."""
        query_lower = query.lower()

        workflow_keywords = [
            "multi-step",
            "workflow",
            "process with approval",
            "long-running task",
            "resume later",
        ]

        return any(kw in query_lower for kw in workflow_keywords)
