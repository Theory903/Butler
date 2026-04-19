from core.errors import Problem

class OrchestratorErrors:
    WORKFLOW_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/workflow-not-found",
        title="Workflow Not Found",
        status=404,
    )
    APPROVAL_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/approval-not-found",
        title="Approval Request Not Found",
        status=404,
    )

    @staticmethod
    def invalid_transition(from_s: str, to_s: str) -> Problem:
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/invalid-task-transition",
            title="Invalid Task Transition",
            status=409,
            detail=f"Cannot transition from '{from_s}' to '{to_s}'.",
        )

class ApprovalRequired(Problem):
    def __init__(self, approval_type: str, description: str):
        super().__init__(
            type="https://docs.butler.lasmoid.ai/problems/approval-required",
            title="Approval Required",
            status=402, # Payment Required/Action Required semantics
            detail=description,
            approval_type=approval_type
        )
