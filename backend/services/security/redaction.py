import logging
import re

logger = logging.getLogger(__name__)


class RedactionService:
    """Butler PII Redactor (v3.1).

    Uses high-performance regex patterns to mask sensitive data
    before it leaves the sovereign boundary (e.g. to OpenAI/Anthropic).
    """

    # Priority patterns
    PATTERNS = {
        "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
        "API_KEY": r"(?:sk|pk|ak|key|auth|token)[-_a-zA-Z0-9]{20,}",
        "IPV4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    }

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._compiled_patterns = {name: re.compile(pat) for name, pat in self.PATTERNS.items()}

    def redact(self, text: str) -> tuple[str, dict[str, list[str]]]:
        """Redact PII from text.

        Returns:
            (redacted_text, redaction_map)
            redaction_map stores the original strings for possible reversal.
        """
        if not self.enabled:
            return text, {}

        redacted_text = text
        redaction_map = {}

        for name, pattern in self._compiled_patterns.items():
            matches = list(set(pattern.findall(redacted_text)))
            if matches:
                if name not in redaction_map:
                    redaction_map[name] = []

                for i, match in enumerate(matches):
                    placeholder = f"<{name}_{i}>"
                    redacted_text = redacted_text.replace(match, placeholder)
                    redaction_map[name].append(match)

        return redacted_text, redaction_map

    def restore(self, redacted_text: str, redaction_map: dict[str, list[str]]) -> str:
        """Restore redacted placeholders with original values."""
        restored_text = redacted_text
        for name, values in redaction_map.items():
            for i, original in enumerate(values):
                placeholder = f"<{name}_{i}>"
                restored_text = restored_text.replace(placeholder, original)
        return restored_text
