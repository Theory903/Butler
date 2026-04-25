"""
Schema normalization for Hermes tools.

Converts Hermes tool schemas into Butler-compatible formats.
"""

from __future__ import annotations

from typing import Any


def normalize_hermes_schema(hermes_schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Hermes tool schema into Butler-compatible format.

    Hermes uses OpenAI-style function schemas. This ensures they conform
    to Butler's schema requirements.

    Args:
        hermes_schema: Raw schema from Hermes tool

    Returns:
        Normalized schema compatible with Butler
    """
    normalized = {
        "name": hermes_schema.get("name", ""),
        "description": hermes_schema.get("description", ""),
    }

    # Normalize parameters
    params = hermes_schema.get("parameters", {})
    if params:
        normalized["parameters"] = {
            "type": params.get("type", "object"),
            "properties": params.get("properties", {}),
            "required": params.get("required", []),
        }

    return normalized


def extract_tool_name_from_schema(hermes_schema: dict[str, Any]) -> str:
    """Extract tool name from Hermes schema."""
    return hermes_schema.get("name", "")


def extract_tool_description_from_schema(hermes_schema: dict[str, Any]) -> str:
    """Extract tool description from Hermes schema."""
    return hermes_schema.get("description", "")


def extract_tool_parameters_from_schema(hermes_schema: dict[str, Any]) -> dict[str, Any]:
    """Extract parameters from Hermes schema."""
    return hermes_schema.get("parameters", {})
