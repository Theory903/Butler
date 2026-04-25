from core.errors import Problem


class ToolErrors:
    @staticmethod
    def timeout(tool_name: str, timeout_seconds: int) -> Problem:
        return Problem(
            type="tool-timeout",
            title="Tool Timeout",
            status=504,
            detail=f"Tool '{tool_name}' timed out after {timeout_seconds}s.",
        )

    @staticmethod
    def precondition_failed(reason: str) -> Problem:
        return Problem(
            type="precondition-failed",
            title="Precondition Failed",
            status=422,
            detail=f"Tool pre-execution checks failed: {reason}",
        )

    @staticmethod
    def service_degraded(detail: str) -> Problem:
        return Problem(
            type="service-degraded",
            title="Service Degraded",
            status=503,
            detail=detail,
        )
