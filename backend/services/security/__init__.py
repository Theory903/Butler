from .trust import TrustClassifier, ChannelSeparator
from .defense import ContentDefense
from .policy import PolicyDecisionPoint, ToolCapabilityGate, MemoryIsolation
from .crypto import AESCipher, KeyHierarchy

class SecurityService:
    def __init__(self):
        self.trust = TrustClassifier()
        self.channel = ChannelSeparator()
        self.defense = ContentDefense()
        self.pdp = PolicyDecisionPoint()
        self.tool_gate = ToolCapabilityGate()
        self.memory_isolation = MemoryIsolation()

    async def evaluate_policy(self, input):
        return await self.pdp.evaluate(input)
    
    async def evaluate_content(self, content: str, source_type: str):
        content_src = self.trust.classify_content(content, source_type)
        return await self.defense.evaluate(content, content_src)
    
    async def validate_tool_request(self, request, actor):
        return await self.tool_gate.validate(request, actor)

__all__ = [
    "TrustClassifier",
    "ChannelSeparator",
    "ContentDefense",
    "PolicyDecisionPoint",
    "ToolCapabilityGate",
    "MemoryIsolation",
    "AESCipher",
    "KeyHierarchy",
    "SecurityService"
]
