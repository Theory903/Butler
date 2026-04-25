from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Oracle-Grade v2.0 Rule: Only allowstated binaries can be executed by the Tools service.
# This prevents trivial escalation if an LLM manages to bypass parameter validation.
SAFE_BINS: set[str] = {
    "/usr/bin/git",
    "/usr/bin/ls",
    "/usr/bin/cat",
    "/usr/bin/grep",
    "/usr/bin/curl",
    "/usr/bin/sed",
    "/usr/bin/awk",
    "/usr/bin/python3",
    "/usr/local/bin/gh",
    "/usr/local/bin/python3",
    "/opt/homebrew/bin/python3",
    "/opt/homebrew/bin/node",
    "git",  # If in PATH and resolved to a safe location
    "python3",
}


class ToolAuditor:
    """Security auditor for tool execution.

    Ported from OpenClaw v3.1 Oracle-Grade patterns:
    - Binary allowlisting (SafeBin).
    - Executable path resolution & validation.
    - OTEL audit logging for every execution.
    """

    def __init__(self, additional_safe_bins: list[str] | None = None) -> None:
        self.safe_bins = SAFE_BINS.copy()
        if additional_safe_bins:
            self.safe_bins.update(additional_safe_bins)

    def is_safe_binary(self, binary: str) -> bool:
        """Verify if a binary is in the SafeBin allowlist."""
        # Normalize: if it's just a name, resolve it
        path = Path(binary)

        # If it's a relative path or just a command name, we check if it's explicitly allowed
        if not path.is_absolute():
            if str(path) in self.safe_bins:
                return True
            # Try to resolve via PATH
            import shutil

            resolved = shutil.which(str(path))
            if not resolved:
                return False
            path = Path(resolved)

        return str(path) in self.safe_bins

    def audit_execution(self, command: list[str], account_id: str) -> None:
        """Log the execution for security monitoring."""
        if not command:
            return

        binary = command[0]
        is_safe = self.is_safe_binary(binary)

        logger.info(
            "tool_execution_audited",
            binary=binary,
            command=" ".join(command[:3]) + ("..." if len(command) > 3 else ""),
            account_id=account_id,
            safe=is_safe,
        )

        if not is_safe:
            logger.warning("unsafe_tool_execution_blocked", binary=binary, account_id=account_id)
            raise PermissionError(f"Execution of binary '{binary}' is blocked by SafeBin policy.")
