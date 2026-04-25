"""Openclaw Skills Library Loader.

Loads SKILL.md files from `backend/skills_library/` (copied from openclaw)
and converts them to Butler skill definitions for the ButlerSkillCompiler.

Each openclaw SKILL.md has YAML frontmatter:
  ---
  name: skill-name
  description: ...
  metadata:
    openclaw:
      emoji: ...
      requires: { bins: [...] }
      install: [...]
  ---
  # Skill body (markdown)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default location for openclaw-derived skills
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills_library"


@dataclass
class OpenclawSkill:
    """Parsed openclaw SKILL.md."""

    name: str
    description: str
    body: str
    metadata: dict[str, Any]
    source_path: Path

    @property
    def emoji(self) -> str:
        return self.metadata.get("openclaw", {}).get("emoji", "")

    @property
    def required_bins(self) -> list[str]:
        return self.metadata.get("openclaw", {}).get("requires", {}).get("bins", [])

    @property
    def install_steps(self) -> list[dict[str, Any]]:
        return self.metadata.get("openclaw", {}).get("install", [])


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-ish frontmatter from a SKILL.md.

    Returns (frontmatter_dict, body). Falls back to empty dict if PyYAML missing
    or frontmatter is malformed.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text

    raw_fm, body = match.group(1), match.group(2)

    try:
        import yaml

        parsed = yaml.safe_load(raw_fm) or {}
        if not isinstance(parsed, dict):
            parsed = {}
        return parsed, body
    except ImportError:
        logger.warning("pyyaml_not_installed: frontmatter not parsed for skill loader")
        return {}, body
    except Exception as e:
        logger.error(f"frontmatter_parse_failed: {e}")
        return {}, body


def load_skill(skill_md_path: Path) -> OpenclawSkill | None:
    """Load a single openclaw SKILL.md file.

    Args:
        skill_md_path: Path to a SKILL.md file

    Returns:
        Parsed OpenclawSkill or None on error
    """
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"skill_read_failed: path={skill_md_path}, error={e}")
        return None

    frontmatter, body = _parse_frontmatter(text)

    name = frontmatter.get("name") or skill_md_path.parent.name
    description = frontmatter.get("description", "")
    metadata = {k: v for k, v in frontmatter.items() if k not in ("name", "description")}

    return OpenclawSkill(
        name=name,
        description=description,
        body=body,
        metadata=metadata,
        source_path=skill_md_path,
    )


def discover_skills(skills_dir: Path | None = None) -> list[OpenclawSkill]:
    """Discover all SKILL.md files under a directory.

    Args:
        skills_dir: Skills root directory (defaults to backend/skills_library)

    Returns:
        List of parsed OpenclawSkill
    """
    base = skills_dir or DEFAULT_SKILLS_DIR
    if not base.exists():
        logger.warning(f"skills_dir_missing: path={base}")
        return []

    skills: list[OpenclawSkill] = []
    for skill_md in base.glob("*/SKILL.md"):
        skill = load_skill(skill_md)
        if skill is not None:
            skills.append(skill)

    logger.info(f"openclaw_skills_discovered: count={len(skills)}, dir={base}")
    return skills


def to_butler_skill_definition(skill: OpenclawSkill) -> dict[str, Any]:
    """Convert an OpenclawSkill into a Butler SkillDefinition payload.

    Compatible with ButlerSkillCompiler.register_skill().
    """
    return {
        "name": skill.name,
        "description": skill.description,
        "category": "openclaw",
        "tags": skill.required_bins,
        "metadata": {
            "emoji": skill.emoji,
            "install": skill.install_steps,
            "source": str(skill.source_path),
        },
        "body": skill.body,
    }


def load_all_into_compiler(compiler: Any, skills_dir: Path | None = None) -> int:
    """Load every openclaw skill into a ButlerSkillCompiler instance.

    Args:
        compiler: A ButlerSkillCompiler-like object exposing register_skill(...)
        skills_dir: Optional skills root (defaults to backend/skills_library)

    Returns:
        Number of skills registered.
    """
    skills = discover_skills(skills_dir)
    registered = 0

    for skill in skills:
        try:
            payload = to_butler_skill_definition(skill)
            if hasattr(compiler, "register_skill"):
                compiler.register_skill(**payload)
            elif hasattr(compiler, "register"):
                compiler.register(payload)
            else:
                logger.warning(f"compiler_missing_register_method: skill={skill.name}")
                continue
            registered += 1
        except Exception as e:
            logger.error(f"skill_registration_failed: skill={skill.name}, error={e}")

    logger.info(f"openclaw_skills_registered: count={registered}")
    return registered
