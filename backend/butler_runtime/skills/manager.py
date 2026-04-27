"""Butler Skills Manager.

Manages skills (pre-built tool sets) with Butler governance.
"""

import logging
from pathlib import Path

from .registry import ButlerSkillSpec, ButlerSkillsRegistry

import structlog

logger = structlog.get_logger(__name__)


class ButlerSkillsManager:
    """Manager for Butler skills.

    Handles skill discovery, loading, and governance.
    """

    def __init__(self, registry: ButlerSkillsRegistry | None = None) -> None:
        """Initialize skills manager.

        Args:
            registry: Optional skills registry (creates new if not provided)
        """
        self._registry = registry or ButlerSkillsRegistry()
        self._hermes_skills_path: Path | None = None

    def set_hermes_skills_path(self, path: Path) -> None:
        """Set path to Hermes skills directory.

        Args:
            path: Path to Hermes skills directory
        """
        self._hermes_skills_path = path

    def discover_hermes_skills(self) -> list[ButlerSkillSpec]:
        """Discover skills from Hermes directory.

        Returns:
            List of discovered skill specifications
        """
        if not self._hermes_skills_path or not self._hermes_skills_path.exists():
            logger.warning("Hermes skills path not set or does not exist")
            return []

        discovered = []

        for category_dir in self._hermes_skills_path.iterdir():
            if not category_dir.is_dir():
                continue

            if category_dir.name.startswith("."):
                continue

            category = category_dir.name

            # Scan for skill manifests
            for skill_file in category_dir.glob("*.json"):
                try:
                    spec = self._load_hermes_skill(skill_file, category)
                    if spec:
                        discovered.append(spec)
                except Exception as e:
                    logger.exception(f"Failed to load skill from {skill_file}: {e}")

        # Register discovered skills
        for spec in discovered:
            self._registry.register_hermes_skill(
                name=spec.name,
                description=spec.description,
                category=spec.category,
                tools=spec.tools,
                risk_tier=spec.risk_tier,
            )

        logger.info(f"Discovered {len(discovered)} Hermes skills")
        return discovered

    def _load_hermes_skill(self, skill_file: Path, category: str) -> ButlerSkillSpec | None:
        """Load a Hermes skill from file.

        Args:
            skill_file: Path to skill JSON file
            category: Skill category

        Returns:
            ButlerSkillSpec or None if loading failed
        """
        import json

        try:
            with open(skill_file) as f:
                data = json.load(f)

            # Extract skill metadata
            name = data.get("name", skill_file.stem)
            description = data.get("description", "")
            tools = data.get("tools", [])

            # Determine risk tier based on category
            risk_tier = self._determine_risk_tier(category)

            return ButlerSkillSpec(
                name=name,
                description=description,
                category=category,
                tools=tools,
                risk_tier=risk_tier,
                source="hermes",
                metadata={"original_file": str(skill_file)},
            )

        except Exception as e:
            logger.exception(f"Failed to parse skill file {skill_file}: {e}")
            return None

    def _determine_risk_tier(self, category: str) -> str:
        """Determine risk tier based on category.

        Args:
            category: Skill category

        Returns:
            Risk tier (low, medium, high, critical)
        """
        high_risk_categories = {"shell", "system", "red-teaming", "autonomous-ai-agents"}
        medium_risk_categories = {"github", "devops", "mlops", "software-development"}

        if category in high_risk_categories:
            return "high"
        if category in medium_risk_categories:
            return "medium"
        return "low"

    def get_registry(self) -> ButlerSkillsRegistry:
        """Get the skills registry.

        Returns:
            ButlerSkillsRegistry instance
        """
        return self._registry

    def get_skill(self, name: str) -> ButlerSkillSpec | None:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill specification or None
        """
        return self._registry.get(name)

    def get_skills_for_category(self, category: str) -> list[ButlerSkillSpec]:
        """Get all skills for a category.

        Args:
            category: Skill category

        Returns:
            List of skill specifications
        """
        return self._registry.get_by_category(category)

    def get_visible_skills(
        self,
        account_tier: str = "free",
        risk_tier_limit: str = "critical",
    ) -> list[ButlerSkillSpec]:
        """Get visible skills for a context.

        Args:
            account_tier: Account tier
            risk_tier_limit: Maximum risk tier

        Returns:
            List of visible skill specifications
        """
        return self._registry.get_visible(account_tier, risk_tier_limit)

    def enable_skill(self, name: str) -> bool:
        """Enable a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was enabled
        """
        return self._registry.enable(name)

    def disable_skill(self, name: str) -> bool:
        """Disable a skill.

        Args:
            name: Skill name

        Returns:
            True if skill was disabled
        """
        return self._registry.disable(name)
