"""Butler Skill Registry.

Phase E.1: Registry for compiled skills.
Manages skill registration, discovery, and lifecycle.
"""

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ButlerSkillRegistry:
    """Registry for compiled Butler skills.

    This registry:
    - Manages skill registration and discovery
    - Tracks skill metadata and status
    - Provides skill lookup by category and name
    - Integrates with HermesDispatcher for tool registration
    """

    def __init__(self, hermes_dispatcher: Any | None = None):
        """Initialize the skill registry.

        Args:
            hermes_dispatcher: Butler's HermesDispatcher instance
        """
        self._hermes_dispatcher = hermes_dispatcher
        self._skills: dict[str, dict[str, Any]] = {}
        self._categories: dict[str, set[str]] = {}

    def register_skill(self, skill_spec: dict[str, Any]) -> None:
        """Register a compiled skill.

        Args:
            skill_spec: Compiled ButlerToolSpec
        """
        skill_name = skill_spec.get("name")
        if not skill_name:
            logger.warning("skill_registration_failed", reason="missing_name")
            return

        self._skills[skill_name] = skill_spec

        # Track by category
        category = skill_spec.get("category", "uncategorized")
        if category not in self._categories:
            self._categories[category] = set()
        self._categories[category].add(skill_name)

        # Register with HermesDispatcher if available
        if self._hermes_dispatcher:
            try:
                self._hermes_dispatcher.register_tool(skill_spec)
            except Exception:
                logger.bind(skill_name=skill_name).exception("hermes_dispatcher_registration_failed")

        logger.bind(skill_name=skill_name, category=category).info("skill_registered")

    def unregister_skill(self, skill_name: str) -> None:
        """Unregister a skill.

        Args:
            skill_name: Name of skill to unregister
        """
        if skill_name in self._skills:
            skill = self._skills[skill_name]
            category = skill.get("category", "uncategorized")

            del self._skills[skill_name]

            if category in self._categories and skill_name in self._categories[category]:
                self._categories[category].remove(skill_name)

            logger.bind(skill_name=skill_name).info("skill_unregistered")

    def get_skill(self, skill_name: str) -> dict[str, Any] | None:
        """Get a skill by name.

        Args:
            skill_name: Name of skill

        Returns:
            Skill spec or None
        """
        return self._skills.get(skill_name)

    def list_skills(self, category: str | None = None) -> list[dict[str, Any]]:
        """List skills, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of skill specs
        """
        if category:
            skill_names = self._categories.get(category, set())
            return [self._skills[name] for name in skill_names if name in self._skills]
        return list(self._skills.values())

    def list_categories(self) -> list[str]:
        """List all skill categories.

        Returns:
            List of category names
        """
        return list(self._categories.keys())

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        """Search skills by name or description.

        Args:
            query: Search query

        Returns:
            List of matching skill specs
        """
        query_lower = query.lower()
        matches = []

        for skill in self._skills.values():
            name = skill.get("name", "").lower()
            description = skill.get("description", "").lower()

            if query_lower in name or query_lower in description:
                matches.append(skill)

        return matches

    def get_skill_count(self) -> int:
        """Get total number of registered skills.

        Returns:
            Number of skills
        """
        return len(self._skills)

    def get_category_count(self) -> int:
        """Get number of categories.

        Returns:
            Number of categories
        """
        return len(self._categories)
