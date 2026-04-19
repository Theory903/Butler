"""Butler Skills exposed as LLM tools for Hermes.

This allows the Butler to browse available skills and retrieve execution plans,
effectively allowing the agent to "learn" how to execute pre-packaged workflows.
"""

from .registry import registry, tool_result, tool_error

def _get_catalog():
    from domain.skills.skills_catalog import make_default_skills_catalog
    return make_default_skills_catalog()

registry.register(
    name="list_skills",
    toolset="skills",
    description="List all available Butler skills and their descriptions.",
    schema={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Optional domain filter (e.g. 'productivity', 'research')",
            }
        },
    },
    handler=lambda args: tool_result(_get_catalog().list_skills(args.get("domain"))),
)

registry.register(
    name="get_skill_plan",
    toolset="skills",
    description="Get the execution plan and description for a specific skill.",
    schema={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "The exact name of the skill to retrieve",
            }
        },
        "required": ["skill_name"],
    },
    handler=lambda args: _get_skill_plan(args)
)

def _get_skill_plan(args):
    skill_name = args.get("skill_name")
    skill = _get_catalog().get_skill(skill_name)
    if not skill:
        return tool_error(f"Skill '{skill_name}' not found. Use list_skills to see available skills.")
    
    return tool_result(skill)
