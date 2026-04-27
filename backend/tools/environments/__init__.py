"""Shim package that re-exports environments from the hermes integration.

This allows code that imports ``from tools.environments.base import ...``
to find the real implementation in ``integrations.hermes.tools.environments``.
"""

# Re-export all public API from the real implementation
from integrations.hermes.tools.environments.base import (
    BaseEnvironment,
    ProcessHandle,
    _file_mtime_key,
    _get_activity_callback,
    _load_json_store,
    _pipe_stdin,
    _popen_bash,
    _save_json_store,
    _ThreadedProcessHandle,
    get_sandbox_dir,
    set_activity_callback,
    touch_activity_if_due,
)

__all__ = [
    "BaseEnvironment",
    "ProcessHandle",
    "_ThreadedProcessHandle",
    "get_sandbox_dir",
    "set_activity_callback",
    "touch_activity_if_due",
    "_get_activity_callback",
    "_pipe_stdin",
    "_popen_bash",
    "_load_json_store",
    "_save_json_store",
    "_file_mtime_key",
]
