from domain.security.models import ContentSource, DefenseDecision, TrustLevel

from .trust import ChannelSeparator


class ContentDefense:
    """Multi-signal injection detection — pattern matching is ONE weak signal, not religion."""

    DETECTION_SIGNALS = {
        "ignore_instructions": ["ignore previous", "disregard", "forget instructions"],
        "role_confusion": ["you are now", "pretend to be", "roleplay as"],
        "context_injection": ["in the text above", "as mentioned before"],
        "channel_escalation": ["system prompt", "hidden instructions"],
        "tool_injection": ["execute", "run command", "shell", "bash"],
        "obfuscation": ["base64", "hex encoding", "url encoding"],
    }

    RESPONSE_ACTIONS = {
        "tag_suspicious": "Content marked untrusted",
        "lower_trust": "Trust score reduced",
        "exclude_high_authority": "Blocked from instruction channel",
        "require_approval": "Human approval required",
        "quarantine": "Security event logged, content isolated",
        "block": "High-confidence attack blocked",
    }

    async def evaluate(self, content: str, source: ContentSource) -> DefenseDecision:
        # 1. Base trust from source
        trust = self._get_base_trust(source)

        # 2. Pattern detection (weak signal)
        signals = self._detect_injection_patterns(content)

        # 3. Adjust trust
        if signals:
            trust *= 0.5

        # 4. Decide channel assignment
        if trust < 0.3:
            channel = "quarantine"
            block = True
        elif trust < 0.6:
            channel = "data_context"
            block = False
        else:
            channel = ChannelSeparator().route_to_channel(source)
            block = False

        return DefenseDecision(
            trust_score=trust,
            channel_assignment=channel,
            response_action=self._decide_response(trust, signals),
            suspicious_signals=signals,
            block=block,
        )

    def _detect_injection_patterns(self, content: str) -> list[str]:
        content_lower = content.lower()
        found = []
        for signal_type, patterns in self.DETECTION_SIGNALS.items():
            if any(p in content_lower for p in patterns):
                found.append(signal_type)
        return found

    def _get_base_trust(self, source: ContentSource) -> float:
        trust_scores = {
            TrustLevel.TRUSTED: 1.0,
            TrustLevel.INTERNAL: 0.95,
            TrustLevel.USER_INPUT: 0.8,
            TrustLevel.RETRIEVED: 0.7,
            TrustLevel.EXTERNAL: 0.5,
            TrustLevel.UNTRUSTED: 0.2,
        }
        return trust_scores.get(source.trust_level, 0.2)

    def _decide_response(self, trust: float, signals: list[str]) -> str:
        if trust < 0.3:
            return self.RESPONSE_ACTIONS["quarantine"]
        if signals:
            return self.RESPONSE_ACTIONS["lower_trust"]
        return "allowed"
