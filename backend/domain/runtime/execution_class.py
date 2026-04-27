"""Execution class enum for Butler production runtime.

Defines the different execution lanes for handling requests.
Not every task gets LLM. Not every task gets LangGraph.
Not every task gets 39 tools.
Do not turn "what time is it" into a distributed systems tragedy.
"""

from __future__ import annotations

from enum import Enum


class ExecutionClass(str, Enum):
    """Execution class for routing requests to appropriate execution lane."""

    # Direct static response without any computation
    DIRECT_RESPONSE = "direct_response"

    # Deterministic tool execution (L0/L1 tools like get_time)
    DETERMINISTIC_TOOL = "deterministic_tool"

    # LLM answer without tools
    LLM_ANSWER = "llm_answer"

    # LLM with tool planning and execution
    LLM_WITH_TOOLS = "llm_with_tools"

    # Durable LangGraph workflow for multi-step, checkpointed execution
    DURABLE_WORKFLOW = "durable_workflow"

    # Async job for long-running tasks
    ASYNC_JOB = "async_job"

    # Human approval workflow for L2/L3 actions
    HUMAN_APPROVAL_WORKFLOW = "human_approval_workflow"

    # CrewAI multi-agent collaboration for complex tasks
    CREW_MULTI_AGENT = "crew_multi_agent"


class RetrievalMode(str, Enum):
    """Retrieval mode for RAG/KAG context building."""

    NONE = "none"
    RAG = "rag"
    KAG = "kag"
    HYBRID = "hybrid"


# Execution class routing rules
# DIRECT_RESPONSE: static answers, health checks, simple queries
# DETERMINISTIC_TOOL: time, math, local deterministic functions (T0 provider)
# LLM_ANSWER: normal conversation, Q&A without external tools
# LLM_WITH_TOOLS: agentic tool planning, research, multi-step reasoning
# DURABLE_WORKFLOW: long-running, human-in-the-loop, checkpointed workflows
# ASYNC_JOB: browser automation, file indexing, heavy scraping, batch processing
# HUMAN_APPROVAL_WORKFLOW: L2/L3 actions requiring explicit approval
# CREW_MULTI_AGENT: multi-agent collaboration using CrewAI for complex tasks
