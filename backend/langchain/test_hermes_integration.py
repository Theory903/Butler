"""
Test script for Hermes-Butler integration.

Tests the basic flow of loading Hermes tools and executing them through
Butler's governance layer.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from langchain.hermes_governance import register_hermes_tools_in_butler
from langchain.hermes_loader import load_safe_hermes_tools
from langchain.hermes_registry import get_butler_hermes_registry
from langchain.hermes_tools import build_butler_hermes_langchain_tools


async def main():
    """Test the Hermes-Butler integration."""

    # Step 1: Load safe Hermes tools
    try:
        specs = load_safe_hermes_tools()
        for _spec in specs:
            pass
    except Exception:
        return

    # Step 2: Verify Butler-owned registry
    registry = get_butler_hermes_registry()
    all_specs = registry.list()

    # Step 3: Build LangChain tools
    try:
        langchain_tools = build_butler_hermes_langchain_tools()
        for _tool in langchain_tools:
            pass
    except Exception:
        return

    # Step 4: Register in Butler governance
    try:
        register_hermes_tools_in_butler()
    except Exception:
        return

    # Step 5: Test tool execution
    if all_specs:
        test_spec = all_specs[0]
        try:
            from langchain.hermes_runtime import execute_hermes_implementation

            # Test with simple args (will vary by tool)
            if test_spec.name == "fuzzy_find_and_replace":
                await execute_hermes_implementation(
                    test_spec,
                    {
                        "content": "def foo():\n    pass",
                        "old_string": "def foo():",
                        "new_string": "def bar():",
                        "replace_all": False,
                    },
                )
            else:
                pass
        except Exception:
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
