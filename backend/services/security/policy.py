from dataclasses import dataclass
from domain.security.models import PolicyInput, PolicyDecision, ToolGateRequest, ToolGateDecision, ActorContext, RetrievalDecision

@dataclass
class CapabilityScope:
    credential_mode: str
    approval_class: str
    side_effect_class: str
    idempotency_required: bool

class PolicyDecisionPoint:
    """OPA-compatible policy evaluation engine.
    
    Phase 6 initial: Python-based policy evaluation.
    Production: Can be backed by OPA server.
    """
    
    async def evaluate(self, input: PolicyInput) -> PolicyDecision:
        """Evaluate policy for an action request."""
        
        # Deny untrusted content in planning
        if input.content_trust_level == "untrusted" and input.action == "plan:create":
            return PolicyDecision(allow=False, reason="Untrusted content cannot create plans")
        
        # Financial actions require step-up auth
        if input.action.startswith("financial:") and input.assurance_level != "aal2":
            return PolicyDecision(
                allow=False,
                reason="Financial actions require AAL2",
                obligations=["require_step_up"],
            )
        
        # Physical device control requires explicit approval
        if input.action.startswith("device:") and input.action != "device:view":
            if input.approval_state != "approved":
                return PolicyDecision(
                    allow=False,
                    reason="Device control requires approval",
                    obligations=["require_approval"],
                )
        
        # External communication requires approval
        if input.action.startswith("communication:"):
            if input.approval_state != "approved":
                return PolicyDecision(
                    allow=False,
                    reason="External communication requires approval",
                    obligations=["require_approval"],
                )
        
        # Allow safe reads
        if input.action.endswith(":read") and input.content_trust_level != "untrusted":
            return PolicyDecision(allow=True, reason="Safe read allowed")
        
        # Default: allow with logging
        return PolicyDecision(allow=True, reason="Default allow")

class ToolCapabilityGate:
    """Scoped capability validation for tool execution."""

    def __init__(self):
        self._capabilities = {
            "web_search": CapabilityScope("none", "none", "read", False),
            "send_email": CapabilityScope("oauth", "explicit", "write", True),
        }
    
    async def validate(self, request: ToolGateRequest, actor: ActorContext) -> ToolGateDecision:
        # 1. Check capability scope exists
        capability = self._capabilities.get(request.scope)
        if not capability:
            return ToolGateDecision(allowed=False, reason="Unknown capability scope")
        
        # 2. Check credential mode
        if not self._check_credential(actor, capability.credential_mode):
            return ToolGateDecision(allowed=False, reason="Invalid credential mode")
        
        # 3. Check approval requirement
        if capability.approval_class == "explicit" and not request.approval_token:
            return ToolGateDecision(allowed=False, reason="Requires approval", requires_approval=True)
        
        # 4. Check idempotency for side effects
        if capability.side_effect_class != "read" and capability.idempotency_required:
            if not request.idempotency_key:
                return ToolGateDecision(allowed=False, reason="Idempotency key required")
        
        return ToolGateDecision(allowed=True)

    def _check_credential(self, actor: ActorContext, mode: str) -> bool:
        return True

class MemoryIsolation:
    """Purpose-bound memory retrieval with access classes."""
    
    MEMORY_POLICIES = {
        "public_profile": {"min_assurance": "aal1", "raw_access": True, "redaction": False},
        "preferences": {"min_assurance": "aal1", "raw_access": True, "redaction": False},
        "communication": {"min_assurance": "aal1", "raw_access": False, "redaction": True},
        "auth_security": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "financial": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "health": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "restricted": {"min_assurance": "aal3", "raw_access": False, "redaction": True},
    }
    
    async def check_retrieval(self, memory_class: str, task_family: str, assurance: str) -> RetrievalDecision:
        policy = self.MEMORY_POLICIES.get(memory_class)
        if not policy:
            return RetrievalDecision(allowed=False, reason="Unknown memory class")
        
        # Check assurance level
        assurance_order = {"aal1": 1, "aal2": 2, "aal3": 3}
        if assurance_order.get(assurance, 0) < assurance_order.get(policy["min_assurance"], 3):
            return RetrievalDecision(allowed=False, reason="Assurance level too low")
        
        access_mode = "raw" if policy["raw_access"] else "summarized"
        return RetrievalDecision(
            allowed=True,
            access_mode=access_mode,
            redaction_required=policy["redaction"],
        )
