"""Graph intake node."""

from __future__ import annotations

from core.tracing import traced
from domain.orchestration.router import AdmissionDecision, OperationRequest, OperationRouter, OperationType
from services.orchestrator.graph_state import ButlerGraphState
from services.orchestrator.nodes.common import merge_state


@traced(span_name="butler.graph.node.intake")
async def intake_node(state: ButlerGraphState, router: OperationRouter | None = None) -> ButlerGraphState:
    """Mark request intake after envelope normalization and route through OperationRouter."""
    envelope = state.get("envelope")
    if not envelope:
        return merge_state(
            state,
            "intake",
            events=[
                *state.get("events", []),
                {
                    "type": "intake_error",
                    "error": "Missing envelope in state",
                },
            ],
        )
    
    # If no router provided, skip admission check and mark as received
    if router is None:
        return merge_state(
            state,
            "intake",
            events=[
                *state.get("events", []),
                {
                    "type": "request_received",
                    "request_id": envelope.request_id,
                    "session_id": envelope.session_id,
                    "execution_path": "default",
                    "admission_decision": "allow",
                },
            ],
        )
    
    # Extract tenant_id and user_id from envelope identity or gateway context
    tenant_id = envelope.identity.tenant_id if envelope.identity else envelope.gateway.tenant_id or envelope.account_id
    user_id = envelope.identity.user_id if envelope.identity else envelope.gateway.authenticated_user_id
    
    # Create OperationRequest for routing
    operation_request = OperationRequest(
        operation_type=OperationType.CHAT,
        tenant_id=tenant_id,
        account_id=envelope.account_id,
        user_id=user_id,
        tool_name=None,
        risk_tier=None,
        estimated_cost=None,
    )
    
    # Route through OperationRouter
    execution_path, admission = router.route(operation_request)
    
    # Check if admission was denied
    if admission.decision != AdmissionDecision.ALLOW:
        return merge_state(
            state,
            "intake",
            events=[
                *state.get("events", []),
                {
                    "type": "request_admitted",
                    "request_id": envelope.request_id,
                    "session_id": envelope.session_id,
                    "admission_decision": admission.decision.value,
                    "admission_reason": admission.reason,
                },
            ],
        )
    
    return merge_state(
        state,
        "intake",
        events=[
            *state.get("events", []),
            {
                "type": "request_received",
                "request_id": envelope.request_id,
                "session_id": envelope.session_id,
                "execution_path": execution_path,
                "admission_decision": admission.decision.value,
            },
        ],
    )
