"""Stub for tools.skills_hub."""
from dataclasses import dataclass
from enum import Enum

class SkillSource(Enum):
    LOCAL = "local"
    REMOTE = "remote"

@dataclass
class SkillSpec:
    name: str
    source: SkillSource
    manifest: dict

class SkillsHub:
    def __init__(self):
        self._skills = {}
    
    def register(self, skill: SkillSpec):
        self._skills[skill.name] = skill
    
    def get(self, name: str):
        return self._skills.get(name)
    
    def list_all(self):
        return list(self._skills.values())

hub = SkillsHub()