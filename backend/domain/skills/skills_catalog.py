"""Butler Skills Catalog — Phase 11, SOLID edition.

Implements ISkillsCatalog. Depends on ISkillsSource (D).
Each source owns one scanning strategy (S).
New sources extend ISkillsSource without touching the catalog (O).
All sources are substitutable (L).
ISkillsCatalog and ISkillsSource are small, focused interfaces (I).

Architecture:
    ButlerSkillsCatalog
        ├── HermesSkillsSource        — integrations/hermes/skills/
        ├── HermesOptionalSkillsSource — integrations/hermes/optional-skills/
        └── [future: RemoteSkillsSource, GitHubSkillsSource, ...]

Each skill dir is expected to co-locate:
  - SKILL.md or skill.yaml   (metadata: name, description, domain, version)
  - __init__.py or run.py    (entry point — optional, loaded lazily)

Skills are tagged with source="hermes" or source="hermes-optional".

Usage:
    catalog = make_default_skills_catalog()
    skills  = catalog.list_skills(domain="productivity")
    skill   = catalog.get_skill("powerpoint")

    # DI / test:
    catalog = ButlerSkillsCatalog([MockSkillsSource()])
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_HERMES_SKILLS_DIR = Path(__file__).parent.parent.parent / "integrations" / "hermes" / "skills"
_HERMES_OPTIONAL_SKILLS_DIR = (
    Path(__file__).parent.parent.parent / "integrations" / "hermes" / "optional-skills"
)


# ── Skill value object ────────────────────────────────────────────────────────


@dataclass
class Skill:
    name: str
    domain: str
    source: str  # "hermes" | "hermes-optional" | "user"
    description: str = ""
    version: str = "1.0"
    path: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── ISkillsSource (small interface — I) ──────────────────────────────────────


class ISkillsSource:
    """Single responsibility: scan one skills directory and return Skill objects."""

    def scan(self) -> list[Skill]:
        raise NotImplementedError


# ── Concrete sources (S, O) ───────────────────────────────────────────────────


class HermesSkillsSource(ISkillsSource):
    """Scans integrations/hermes/skills/ — the standard Hermes skill domains."""

    def scan(self) -> list[Skill]:
        return _scan_skills_root(_HERMES_SKILLS_DIR, source="hermes")


class HermesOptionalSkillsSource(ISkillsSource):
    """Scans integrations/hermes/optional-skills/ — extended skill library."""

    def scan(self) -> list[Skill]:
        return _scan_skills_root(_HERMES_OPTIONAL_SKILLS_DIR, source="hermes-optional")


def _scan_skills_root(root: Path, source: str) -> list[Skill]:
    """Recursively scan a skills root dir.

    Structure: root/domain/skill-name/(SKILL.md or skill.yaml)
    Falls back to directory name as skill name if no metadata file found.
    """
    skills: list[Skill] = []
    if not root.exists():
        return skills

    for domain_dir in sorted(root.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
            continue
        domain = domain_dir.name

        for skill_dir in sorted(domain_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue
            skill = _load_skill(skill_dir, domain=domain, source=source)
            if skill:
                skills.append(skill)
                logger.debug("skill_discovered", name=skill.name, domain=domain, source=source)

    return skills


def _load_skill(skill_dir: Path, domain: str, source: str) -> Skill | None:
    """Load skill metadata from SKILL.md, skill.yaml, or skill.json."""
    name = skill_dir.name
    metadata: dict[str, Any] = {}
    description = ""
    version = "1.0"
    tags: list[str] = []

    # Try skill.yaml first
    yaml_path = skill_dir / "skill.yaml"
    md_path = skill_dir / "SKILL.md"
    json_path = skill_dir / "skill.json"

    try:
        if yaml_path.exists():
            import yaml

            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            name = data.get("name", name)
            description = data.get("description", "")
            version = str(data.get("version", "1.0"))
            tags = data.get("tags", [])
            metadata = data
        elif json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            name = data.get("name", name)
            description = data.get("description", "")
            metadata = data
        elif md_path.exists():
            # Parse front-matter from SKILL.md (--- ... ---)
            content = md_path.read_text(encoding="utf-8")
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    try:
                        import yaml

                        fm = yaml.safe_load(content[3:end]) or {}
                        name = fm.get("name", name)
                        description = fm.get("description", "")
                        version = str(fm.get("version", "1.0"))
                        tags = fm.get("tags", [])
                        metadata = fm
                    except Exception:
                        pass
    except Exception as exc:
        logger.debug("skill_metadata_load_failed", skill=name, error=str(exc))

    return Skill(
        name=name,
        domain=domain,
        source=source,
        description=description,
        version=version,
        path=str(skill_dir),
        tags=tags,
        metadata=metadata,
    )


# ── ButlerSkillsCatalog (ISkillsCatalog, DI-friendly) ─────────────────────────


class ButlerSkillsCatalog:
    """Butler Skills Catalog.

    Depends on ISkillsSource list — injected (D).
    Adding new skill sources = new ISkillsSource, no changes here (O).
    Implements ISkillsCatalog (L).
    """

    def __init__(self, sources: list[ISkillsSource]) -> None:
        self._sources = sources
        self._skills: dict[str, Skill] = {}  # name → Skill
        self._scanned = False

    def scan(self) -> list[dict]:  # ISkillsCatalog — idempotent
        if self._scanned:
            return [self._to_dict(s) for s in self._skills.values()]
        self._scanned = True

        for source in self._sources:
            try:
                for skill in source.scan():
                    # Last source wins on name collision (optional > standard)
                    self._skills[skill.name] = skill
            except Exception as exc:
                logger.warning(
                    "skills_source_scan_failed",
                    source=type(source).__name__,
                    error=str(exc),
                )

        logger.info("butler_skills_scanned", total=len(self._skills))
        return [self._to_dict(s) for s in self._skills.values()]

    def list_skills(self, domain: str | None = None) -> list[dict]:  # ISkillsCatalog
        self.scan()
        skills = self._skills.values()
        if domain:
            skills = (s for s in skills if s.domain == domain)  # type: ignore[assignment]
        return [self._to_dict(s) for s in skills]

    def get_skill(self, name: str) -> dict | None:  # ISkillsCatalog
        self.scan()
        skill = self._skills.get(name)
        return self._to_dict(skill) if skill else None

    def domains(self) -> list[str]:
        """Return sorted list of distinct skill domains."""
        self.scan()
        return sorted({s.domain for s in self._skills.values()})

    def count(self) -> int:
        self.scan()
        return len(self._skills)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(skill: Skill) -> dict:
        return {
            "name": skill.name,
            "domain": skill.domain,
            "source": skill.source,
            "description": skill.description,
            "version": skill.version,
            "path": skill.path,
            "tags": skill.tags,
        }


# ── Default factory ───────────────────────────────────────────────────────────


def make_default_skills_catalog() -> ButlerSkillsCatalog:
    """Production: scans both Hermes skill libraries."""
    return ButlerSkillsCatalog(
        sources=[
            HermesSkillsSource(),
            HermesOptionalSkillsSource(),
        ]
    )
