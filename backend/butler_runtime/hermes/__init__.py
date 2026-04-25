"""Butler-Hermes execution utilities.

This package contains Hermes-derived execution utilities that have been
assimilated into Butler's unified runtime.
"""

from .execution.function_call_handler import FunctionCallHandler
from .execution.tool_schema_converter import convert_hermes_schema_to_butler_spec

__all__ = [
    "convert_hermes_schema_to_butler_spec",
    "FunctionCallHandler",
]
