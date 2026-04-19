"""Hermes plugins and skills catalog - Butler adaptation.

Provides plugin discovery and skill catalog functionality.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ButlerImportedSkillsCatalog:
    """Hermes-style skills catalog for Butler.

    Provides skill discovery and management based on Hermes plugins/skills system.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or (Path.home() / ".butler" / "skills")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, dict] = {}
        self._discover_skills()

    def _discover_skills(self) -> None:
        if not self.skills_dir.exists():
            return
        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "skill.yaml").exists():
                try:
                    import yaml
                    with open(skill_path / "skill.yaml") as f:
                        skill_data = yaml.safe_load(f)
                    self._skills[skill_path.name] = {
                        "name": skill_path.name,
                        "path": str(skill_path),
                        "data": skill_data,
                    }
                except Exception:
                    pass

    def list_skills(self) -> List[dict]:
        return [
            {"name": name, "path": info["path"]}
            for name, info in self._skills.items()
        ]

    def get_skill(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def get_skill_schema(self, name: str) -> Optional[dict]:
        skill = self._skills.get(name)
        if skill and skill.get("data"):
            return skill["data"].get("schema")
        return None


class ButlerImportedPluginRegistry:
    """Hermes-style plugin registry for Butler."""

    def __init__(self):
        self._plugins: Dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        self._plugins[name] = plugin

    def get(self, name: str) -> Optional[Any]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[str]:
        return list(self._plugins.keys())


HermesSkillsCatalog = ButlerImportedSkillsCatalog
HermesPluginRegistry = ButlerImportedPluginRegistry
