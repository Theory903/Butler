"""Stub for tools.registry."""

class ToolRegistry:
    def __init__(self):
        self._tools = {}
    
    def register(self, name, func):
        self._tools[name] = func
    
    def get(self, name):
        return self._tools.get(name)
    
    def list_all(self):
        return list(self._tools.keys())

registry = ToolRegistry()

def tool_error(name: str, error: Exception):
    pass