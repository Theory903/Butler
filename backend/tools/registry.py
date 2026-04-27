"""Stub for tools.registry — accepts full hermes ToolRegistry.register() signature."""

from collections.abc import Callable
from typing import Any


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Any] = {}

    def register(
        self,
        name: str | None = None,
        func: Callable | None = None,
        *,
        toolset: Any = None,
        emoji: Any = None,
        schema: Any = None,
        handler: Any = None,
        check_fn: Any = None,
        **kwargs: Any,
    ) -> None:
        key = name or (handler.__name__ if handler else "unknown")
        self._tools[key] = handler or func

    def get(self, name: str) -> Any:
        return self._tools.get(name)

    def list_all(self) -> list[str]:
        return list(self._tools.keys())


registry = ToolRegistry()


def tool_error(name: str, error: Any = None) -> dict:
    return {"error": str(error), "tool": name}


def tool_result(name: str, data: Any = None) -> dict:
    return {"result": data, "tool": name}
