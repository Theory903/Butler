"""Butler Skill Compiler.

Phase E.1: Compiles skill definitions into Hermes tool specs.
Uses Butler's HermesCompiler to convert skill definitions into ButlerToolSpec.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """A skill definition from openclaw."""

    name: str
    description: str
    category: str
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"  # low, medium, high
    requires_auth: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerSkillCompiler:
    """Compiles skill definitions into Hermes tool specs.

    This compiler:
    - Takes skill definitions (from openclaw or custom)
    - Converts them to HermesToolDef format
    - Uses Butler's HermesCompiler to compile to ButlerToolSpec
    - Registers compiled tools via HermesDispatcher
    """

    def __init__(self, hermes_compiler: Any | None = None):
        """Initialize the skill compiler.

        Args:
            hermes_compiler: Butler's HermesCompiler instance
        """
        self._hermes_compiler = hermes_compiler
        self._skills: dict[str, SkillDefinition] = {}

    def register_skill(self, skill: SkillDefinition) -> None:
        """Register a skill definition.

        Args:
            skill: Skill definition to register
        """
        self._skills[skill.name] = skill
        logger.info("skill_registered", skill_name=skill.name, category=skill.category)

    def compile_skill(self, skill_name: str) -> dict[str, Any] | None:
        """Compile a skill to Hermes tool spec.

        Args:
            skill_name: Name of skill to compile

        Returns:
            Compiled ButlerToolSpec or None
        """
        skill = self._skills.get(skill_name)
        if not skill:
            logger.warning("skill_not_found", skill_name=skill_name)
            return None

        # Convert skill to HermesToolDef format
        hermes_def = {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "parameters": skill.parameters,
            "risk_level": skill.risk_level,
            "requires_auth": skill.requires_auth,
            "metadata": skill.metadata,
        }

        # Compile using Butler's HermesCompiler
        if self._hermes_compiler:
            try:
                from domain.tools.hermes_compiler import HermesToolDef

                tool_def = HermesToolDef(**hermes_def)
                compiled = self._hermes_compiler.compile(tool_def)
                logger.info("skill_compiled", skill_name=skill_name)
                return compiled
            except Exception as e:
                logger.exception("skill_compile_failed", skill_name=skill_name)
                return None

        # Fallback: return the HermesToolDef directly
        return hermes_def

    def compile_all(self) -> list[dict[str, Any]]:
        """Compile all registered skills.

        Returns:
            List of compiled ButlerToolSpec
        """
        compiled_skills = []
        for skill_name in self._skills:
            compiled = self.compile_skill(skill_name)
            if compiled:
                compiled_skills.append(compiled)

        logger.info("all_skills_compiled", count=len(compiled_skills))
        return compiled_skills

    def get_skill(self, skill_name: str) -> SkillDefinition | None:
        """Get a skill definition.

        Args:
            skill_name: Name of skill

        Returns:
            Skill definition or None
        """
        return self._skills.get(skill_name)

    def list_skills(self, category: str | None = None) -> list[SkillDefinition]:
        """List skills, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of skill definitions
        """
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills


# Sample skill definitions (would be ported from openclaw)
SAMPLE_SKILLS = [
    SkillDefinition(
        name="web_search",
        description="Search the web for information",
        category="search",
        parameters={
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "default": 10},
        },
        risk_level="low",
    ),
    SkillDefinition(
        name="file_read",
        description="Read file contents",
        category="file_ops",
        parameters={
            "path": {"type": "string", "description": "File path"},
        },
        risk_level="medium",
    ),
    SkillDefinition(
        name="file_write",
        description="Write content to a file",
        category="file_ops",
        parameters={
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        risk_level="high",
    ),
    SkillDefinition(
        name="calendar_create",
        description="Create a calendar event",
        category="calendar",
        parameters={
            "title": {"type": "string", "description": "Event title"},
            "start_time": {"type": "string", "description": "Start time"},
            "end_time": {"type": "string", "description": "End time"},
        },
        risk_level="low",
    ),
    SkillDefinition(
        name="email_send",
        description="Send an email",
        category="messaging",
        parameters={
            "to": {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body"},
        },
        risk_level="medium",
    ),
]


def load_sample_skills(compiler: ButlerSkillCompiler) -> None:
    """Load sample skills into compiler.

    Args:
        compiler: Skill compiler to load into
    """
    for skill in SAMPLE_SKILLS:
        compiler.register_skill(skill)
    logger.info("sample_skills_loaded", count=len(SAMPLE_SKILLS))
