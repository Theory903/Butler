"""Tool schema converter for Hermes → Butler integration.

Converts Hermes tool schemas to Butler tool specifications.
"""

import logging
from typing import Any

from butler_runtime.tools.registry import ButlerToolSpec

import structlog

logger = structlog.get_logger(__name__)


def convert_hermes_schema_to_butler_spec(
    name: str,
    schema: dict[str, Any],
    category: str = "hermes",
    risk_tier: str = "medium",
) -> ButlerToolSpec:
    """Convert a Hermes tool schema to a Butler tool specification.

    Args:
        name: Tool name
        schema: Hermes tool schema
        category: Tool category (file, web, memory, etc.)
        risk_tier: Risk tier (low, medium, high, critical)

    Returns:
        Butler tool specification

    Note:
        Hermes schemas use a different format than Butler. This function
        normalizes the schema to Butler's expected format.
    """
    # Extract description
    description = schema.get("description", "")

    # Extract parameters (Hermes may use different field names)
    parameters = schema.get("parameters", schema.get("args", {}))

    # Ensure parameters is a valid JSON Schema
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}}

    # Add required fields if missing
    if "type" not in parameters:
        parameters["type"] = "object"
    if "properties" not in parameters:
        parameters["properties"] = {}
    if "required" not in parameters:
        parameters["required"] = []

    # Determine risk tier based on tool category if not provided
    if risk_tier == "medium":
        # Auto-assign risk tier based on category
        high_risk_categories = ["shell", "code", "browser", "system"]
        if category in high_risk_categories:
            risk_tier = "high"
        elif category in ["file"]:
            risk_tier = "medium"
        else:
            risk_tier = "low"

    return ButlerToolSpec(
        name=name,
        description=description,
        parameters=parameters,
        category=category,
        risk_tier=risk_tier,
        source="hermes",
    )


def convert_butler_spec_to_openai_schema(spec: ButlerToolSpec) -> dict[str, Any]:
    """Convert a Butler tool specification to OpenAI function schema format.

    Args:
        spec: Butler tool specification

    Returns:
        OpenAI-style function schema
    """
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def convert_butler_spec_to_anthropic_schema(spec: ButlerToolSpec) -> dict[str, Any]:
    """Convert a Butler tool specification to Anthropic tool use format.

    Args:
        spec: Butler tool specification

    Returns:
        Anthropic-style tool use schema
    """
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.parameters,
    }
