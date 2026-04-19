from core.errors import Problem

class CommunicationErrors:
    @staticmethod
    def policy_blocked(reason: str) -> Problem:
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/communication/policy-blocked",
            title="Communication Policy Blocked",
            status=403,
            detail=f"Message delivery blocked by policy: {reason}"
        )

class ProviderError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
