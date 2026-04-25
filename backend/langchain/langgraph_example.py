"""
LangGraph integration example for Butler-Hermes tools.

This example demonstrates how to use Butler-owned Hermes tools
with LangGraph, showing the complete integration flow from
tool loading through governance to model binding.
"""

import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from langchain.hermes_governance import register_hermes_tools_in_butler
from langchain.hermes_loader import load_safe_hermes_tools
from langchain.hermes_tools import build_butler_hermes_langchain_tools


def example_basic_usage():
    """Basic usage example: Load and use tools."""

    # Load Hermes tool specifications
    hermes_specs = load_safe_hermes_tools()
    for _spec in hermes_specs:
        pass

    # Register in Butler governance
    register_hermes_tools_in_butler()

    # Build LangChain tools
    return build_butler_hermes_langchain_tools()


def example_langgraph_integration():
    """LangGraph integration example: Bind tools to model."""

    # Load tools
    build_butler_hermes_langchain_tools()


def example_file_operations():
    """Example using Butler file operations."""

    from langchain.butler_file_tools import (
        list_files_tool,
    )

    # List files in current directory
    result = list_files_tool(path=".", pattern="*.py", limit=5)
    if "error" in result:
        pass
    else:
        for _file in result.get("files", []):
            pass


def example_web_operations():
    """Example using Butler web operations."""


def main():
    """Run all examples."""

    try:
        example_basic_usage()
        example_langgraph_integration()
        example_file_operations()
        example_web_operations()

    except Exception:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
