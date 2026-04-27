"""Butler Skills Registry.

Registry for skills (pre-built tool sets) with Butler governance.
"""

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ButlerSkillSpec:
    """Butler skill specification.

    Represents a skill (pre-built tool set) in Butler's registry.
    """

    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        tools: list[str],
        risk_tier: str = "medium",
        source: str = "butler",
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize Butler skill specification.

        Args:
            name: Skill name
            description: Skill description
            category: Skill category (e.g., "github", "productivity")
            tools: List of tool names included in this skill
            risk_tier: Risk tier (low, medium, high, critical)
            source: Skill source (butler, hermes, user)
            enabled: Whether skill is enabled
            metadata: Optional metadata
        """
        self.name = name
        self.description = description
        self.category = category
        self.tools = tools
        self.risk_tier = risk_tier
        self.source = source
        self.enabled = enabled
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tools": self.tools,
            "risk_tier": self.risk_tier,
            "source": self.source,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


class ButlerSkillsRegistry:
    """Registry for Butler skills.

    Manages skills (pre-built tool sets) with Butler governance.
    """

    def __init__(self) -> None:
        """Initialize skills registry."""
        self._skills: dict[str, ButlerSkillSpec] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, spec: ButlerSkillSpec) -> None:
        """Register a skill.

        Args:
            spec: Butler skill specification
        """
        self._skills[spec.name] = spec

        # Add to category
        if spec.category not in self._categories:
            self._categories[spec.category] = []
        if spec.name not in self._categories[spec.category]:
            self._categories[spec.category].append(spec.name)

        logger.debug(f"Registered skill: {spec.name} (category: {spec.category})")

    def register_hermes_skill(
        self,
        name: str,
        description: str,
        category: str,
        tools: list[str],
        risk_tier: str = "medium",
    ) -> None:
        """Register a Hermes-derived skill.

        Args:
            name: Skill name
            description: Skill description
            category: Skill category
            tools: List of tool names
            risk_tier: Risk tier
        """
        spec = ButlerSkillSpec(
            name=name,
            description=description,
            category=category,
            tools=tools,
            risk_tier=risk_tier,
            source="hermes",
        )
        self.register(spec)

    def get(self, name: str) -> ButlerSkillSpec | None:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill specification or None if not found
        """
        return self._skills.get(name)

    def get_all(self) -> dict[str, ButlerSkillSpec]:
        """Get all registered skills.

        Returns:
            Dictionary of all skill specifications
        """
        return self._skills.copy()

    def get_by_category(self, category: str) -> list[ButlerSkillSpec]:
        """Get all skills in a category.

        Args:
            category: Skill category

        Returns:
            List of skill specifications
        """
        return [
            self._skills[name]
            for name in self._categories.get(category, [])
            if name in self._skills
        ]

    def get_enabled(self) -> dict[str, ButlerSkillSpec]:
        """Get all enabled skills.

        Returns:
            Dictionary of enabled skill specifications
        """
        return {name: spec for name, spec in self._skills.items() if spec.enabled}

    def get_visible(
        self,
        account_tier: str = "free",
        risk_tier_limit: str = "critical",
    ) -> list[ButlerSkillSpec]:
        """Get visible skills for a context.

        Args:
            account_tier: Account tier (free, pro, enterprise)
            risk_tier_limit: Maximum risk tier to show

        Returns:
            List of visible skill specifications
        """
        risk_hierarchy = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        limit_level = risk_hierarchy.get(risk_tier_limit, 3)

        visible = []
        for spec in self._skills.values():
            if not spec.enabled:
                continue

            # Risk tier check
            spec_level = risk_hierarchy.get(spec.risk_tier, 1)
            if spec_level > limit_level:
                continue

            visible.append(spec)

        return visible

    def enable(self, name: str) -> bool:
        """Enable a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was enabled, False if not found
        """
        if name in self._skills:
            self._skills[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was disabled, False if not found
        """
        if name in self._skills:
            self._skills[name].enabled = False
            return True
        return False

    def unregister(self, name: str) -> bool:
        """Unregister a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was unregistered, False if not found
        """
        if name in self._skills:
            spec = self._skills[name]
            del self._skills[name]

            # Remove from category
            if spec.category in self._categories:
                self._categories[spec.category] = [
                    n for n in self._categories[spec.category] if n != name
                ]

            return True
        return False

    def __len__(self) -> int:
        """Return number of registered skills."""
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if skill is registered."""
        return name in self._skills

    def __repr__(self) -> str:
        return (
            f"ButlerSkillsRegistry(skills={len(self._skills)}, categories={len(self._categories)})"
        )
