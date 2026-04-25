from domain.security.models import ContentSource, TrustLevel

SOURCE_TRUST_MAP = {
    "system_policy": TrustLevel.TRUSTED,
    "workload_internal": TrustLevel.INTERNAL,
    "user_direct_input": TrustLevel.USER_INPUT,
    "memory_episodic": TrustLevel.RETRIEVED,
    "memory_entity": TrustLevel.RETRIEVED,
    "web_content": TrustLevel.EXTERNAL,
    "ocr_output": TrustLevel.EXTERNAL,
    "document_upload": TrustLevel.EXTERNAL,
    "email_body": TrustLevel.EXTERNAL,
    "screenshot_vision": TrustLevel.EXTERNAL,
    "camera_scene_text": TrustLevel.EXTERNAL,
}


class TrustClassifier:
    """Classify every input source by trust level."""

    def classify(self, source_type: str) -> TrustLevel:
        return SOURCE_TRUST_MAP.get(source_type, TrustLevel.UNTRUSTED)

    def classify_content(self, content: str, source_type: str) -> ContentSource:
        return ContentSource(
            source_type=source_type,
            trust_level=self.classify(source_type),
            content_class=self._detect_content_class(content),
            classification_reason=f"Source type: {source_type}",
        )

    def _detect_content_class(self, content: str) -> str:
        return "text"


class ChannelSeparator:
    """Route content to appropriate channel — NEVER merge untrusted into instructions."""

    CHANNELS = {
        "instructions": {
            "trust": TrustLevel.TRUSTED,
            "sources": ["system_policy", "builtin_instructions"],
        },
        "data_context": {
            "trust": TrustLevel.EXTERNAL,
            "sources": ["web_content", "ocr_output", "document_upload"],
        },
        "memory_context": {
            "trust": TrustLevel.RETRIEVED,
            "sources": ["memory_episodic", "memory_entity"],
        },
        "tool_specs": {"trust": TrustLevel.INTERNAL, "sources": ["tool_registry"]},
        "policy_constraints": {"trust": TrustLevel.TRUSTED, "sources": ["security_policy"]},
    }

    def route_to_channel(self, source: ContentSource) -> str:
        for channel, config in self.CHANNELS.items():
            if source.source_type in config["sources"]:
                return channel
        return "data_context"  # Default to lowest trust
