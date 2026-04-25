"""ButlerSkillsHub — Phase 6d.

A skill is a named, versioned bundle of tools + a prompt template that
accomplishes a multi-step goal. Skills sit above individual tools in the
execution hierarchy:

  User intent → OrchestratorService → SkillsHub (match → assemble plan)
                                         ↓
              RuntimeKernel → ButlerToolDispatch (single tool calls)

Think of a skill as a macro: "ResearchAndSummarize" = web_search +
extract + summarise + write_to_memory. The SkillsHub selects the right
skill for an intent label, resolves its tool dependencies, and returns an
execution plan that the Orchestrator's PlanEngine can inject directly.

Sovereignty rules:
  - SkillsHub is Butler-native. No Hermes concept of "skills" leaks in.
  - Skill definitions are stored as plain Python dataclasses in this file.
    In Phase 7+, they migrate to a PostgreSQL `skills` table.
  - SkillsHub NEVER executes tools. It only returns plans.
  - Skill selection is pure (no I/O). Matching is intent-label based.

Built-in skills:
  research_and_summarize  — web search + extract + summarise
  send_message            — compose + send (email/Slack/SMS)
  set_reminder            — parse time + create cron job
  read_and_analyze        — file read + LLM analysis + memory write
  check_status            — multi-source status aggregation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SkillTrigger(StrEnum):
    """How a skill is activated."""

    INTENT_MATCH = "intent_match"  # Matched by intent label
    EXPLICIT_CALL = "explicit_call"  # Explicitly requested by name
    AUTO = "auto"  # Hub decides automatically


@dataclass(frozen=True)
class ToolStep:
    """A single tool invocation within a skill's execution plan."""

    tool_name: str
    params_template: dict  # Template — {key: "{variable}"} filled at runtime
    depends_on: list[str] = field(default_factory=list)  # Step IDs this step waits for
    optional: bool = False
    store_result_as: str | None = None  # Variable name for downstream steps
    timeout_s: int = 30


@dataclass(frozen=True)
class SkillDefinition:
    """Immutable skill blueprint."""

    id: str
    name: str
    description: str
    version: str
    trigger: SkillTrigger
    intent_labels: list[str]  # Which intent labels activate this skill
    steps: list[ToolStep]
    requires_tools: list[str]  # Tool names this skill depends on
    aal_required: str = "aal1"  # Minimum assurance level
    requires_approval: bool = False
    category: str = "general"


@dataclass
class SkillExecutionPlan:
    """Produced by SkillsHub.match(). Consumed by PlanEngine."""

    skill_id: str
    skill_name: str
    steps: list[ToolStep]
    resolved_params: dict[str, Any]  # Params resolved from user message + context
    requires_approval: bool
    aal_required: str


# ── Built-in skill library ─────────────────────────────────────────────────────

_BUILTIN_SKILLS: list[SkillDefinition] = [
    SkillDefinition(
        id="research_and_summarize",
        name="Research and Summarize",
        description="Search the web, extract relevant content, and write a concise summary.",
        version="1.0.0",
        trigger=SkillTrigger.INTENT_MATCH,
        intent_labels=["search", "research", "weather", "who_is", "what_is", "news"],
        category="research",
        requires_tools=["web_search", "content_extract", "summarize"],
        steps=[
            ToolStep(
                tool_name="web_search",
                params_template={"query": "{user_message}", "mode": "general"},
                store_result_as="search_results",
            ),
            ToolStep(
                tool_name="summarize",
                params_template={"content": "{search_results}", "max_length": "300"},
                depends_on=["web_search"],
            ),
        ],
    ),
    SkillDefinition(
        id="send_message",
        name="Send Message",
        description="Compose and send a message via email, Slack, or SMS.",
        version="1.0.0",
        trigger=SkillTrigger.INTENT_MATCH,
        intent_labels=["send", "email", "message", "notify"],
        category="communication",
        requires_tools=["compose_message", "send_email"],
        requires_approval=True,
        aal_required="aal1",
        steps=[
            ToolStep(
                tool_name="compose_message",
                params_template={"prompt": "{user_message}", "channel": "{channel}"},
                store_result_as="composed_message",
            ),
            ToolStep(
                tool_name="send_email",
                params_template={
                    "to": "{recipient}",
                    "subject": "{subject}",
                    "body": "{composed_message}",
                },
                depends_on=["compose_message"],
            ),
        ],
    ),
    SkillDefinition(
        id="set_reminder",
        name="Set Reminder",
        description="Parse a natural language time expression and schedule a reminder.",
        version="1.0.0",
        trigger=SkillTrigger.INTENT_MATCH,
        intent_labels=["reminder", "remind", "schedule", "calendar"],
        category="productivity",
        requires_tools=["parse_time", "create_cron_job"],
        steps=[
            ToolStep(
                tool_name="parse_time",
                params_template={"expression": "{user_message}", "timezone": "{user_timezone}"},
                store_result_as="scheduled_time",
            ),
            ToolStep(
                tool_name="create_cron_job",
                params_template={
                    "trigger_at": "{scheduled_time}",
                    "action": "send_notification",
                    "payload": "{user_message}",
                },
                depends_on=["parse_time"],
            ),
        ],
    ),
    SkillDefinition(
        id="read_and_analyze",
        name="Read and Analyze",
        description="Read a file or document and produce a structured analysis.",
        version="1.0.0",
        trigger=SkillTrigger.INTENT_MATCH,
        intent_labels=["read", "analyze", "review", "document"],
        category="analysis",
        requires_tools=["file_read", "summarize", "memory_write"],
        steps=[
            ToolStep(
                tool_name="file_read",
                params_template={"path": "{file_path}"},
                store_result_as="file_content",
            ),
            ToolStep(
                tool_name="summarize",
                params_template={"content": "{file_content}", "mode": "detailed"},
                depends_on=["file_read"],
                store_result_as="analysis",
            ),
            ToolStep(
                tool_name="memory_write",
                params_template={
                    "content": "{analysis}",
                    "memory_type": "document_summary",
                    "importance": "0.7",
                },
                depends_on=["summarize"],
                optional=True,
            ),
        ],
    ),
    SkillDefinition(
        id="check_status",
        name="Check Status",
        description="Aggregate status from multiple sources and report.",
        version="1.0.0",
        trigger=SkillTrigger.INTENT_MATCH,
        intent_labels=["status", "health", "monitor", "is_up"],
        category="monitoring",
        requires_tools=["http_get"],
        steps=[
            ToolStep(
                tool_name="http_get",
                params_template={"url": "{status_url}"},
                store_result_as="status_result",
            ),
        ],
    ),
]


# ── ButlerSkillsHub ────────────────────────────────────────────────────────────


class ButlerSkillsHub:
    """Skill registry and matcher.

    Usage:
        hub = ButlerSkillsHub()
        plan = hub.match(intent_label="search", context={"user_message": "..."})
        if plan:
            # inject plan into PlanEngine
    """

    def __init__(self, extra_skills: list[SkillDefinition] | None = None) -> None:
        self._skills: dict[str, SkillDefinition] = {s.id: s for s in _BUILTIN_SKILLS}
        if extra_skills:
            for skill in extra_skills:
                self._skills[skill.id] = skill

    def match(
        self,
        intent_label: str,
        context: dict[str, Any] | None = None,
    ) -> SkillExecutionPlan | None:
        """Find the best matching skill for an intent label.

        Returns None if no skill matches (caller falls back to raw tool dispatch).
        """
        ctx = context or {}
        for skill in self._skills.values():
            if skill.trigger in (
                SkillTrigger.INTENT_MATCH,
                SkillTrigger.AUTO,
            ) and intent_label.lower() in [lbl.lower() for lbl in skill.intent_labels]:
                logger.info(
                    "skills_hub_match",
                    intent=intent_label,
                    skill_id=skill.id,
                    steps=len(skill.steps),
                )
                return SkillExecutionPlan(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    steps=list(skill.steps),
                    resolved_params=ctx,
                    requires_approval=skill.requires_approval,
                    aal_required=skill.aal_required,
                )
        return None

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)

    def register(self, skill: SkillDefinition) -> None:
        """Register a new skill (or replace an existing one by ID)."""
        self._skills[skill.id] = skill
        logger.info("skill_registered", skill_id=skill.id, version=skill.version)

    def list_skills(self, category: str | None = None) -> list[dict]:
        skills = self._skills.values()
        if category:
            skills = [s for s in skills if s.category == category]
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "category": s.category,
                "intent_labels": s.intent_labels,
                "step_count": len(s.steps),
                "requires_approval": s.requires_approval,
                "aal_required": s.aal_required,
            }
            for s in skills
        ]

    def list_categories(self) -> list[str]:
        return sorted({s.category for s in self._skills.values()})

    @property
    def skill_count(self) -> int:
        return len(self._skills)
