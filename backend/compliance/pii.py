"""PII Detection and Redaction.

Phase L: PII detection and redaction for privacy compliance.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PIIEntity:
    """A detected PII entity."""

    entity_type: str  # email, phone, ssn, credit_card, etc.
    value: str
    start: int
    end: int
    confidence: float = 1.0


class PIIDetector:
    """PII detector for privacy compliance.

    This detector:
    - Detects personally identifiable information
    - Supports multiple entity types
    - Provides confidence scores
    - Uses regex patterns for detection
    """

    def __init__(self):
        """Initialize the PII detector."""
        self._patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "credit_card": r'\b(?:\d[ -]*?){13,16}\b',
            "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        }

    def detect_pii(self, text: str) -> list[PIIEntity]:
        """Detect PII entities in text.

        Args:
            text: Text to analyze

        Returns:
            List of detected PII entities
        """
        entities = []

        for entity_type, pattern in self._patterns.items():
            for match in re.finditer(pattern, text):
                entity = PIIEntity(
                    entity_type=entity_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                )
                entities.append(entity)

        logger.info("pii_detected", count=len(entities))
        return entities

    def has_pii(self, text: str) -> bool:
        """Check if text contains PII.

        Args:
            text: Text to check

        Returns:
            True if PII detected
        """
        entities = self.detect_pii(text)
        return len(entities) > 0


class PIIRedactor:
    """PII redactor for privacy compliance.

    This redactor:
    - Redacts PII entities from text
    - Supports multiple redaction strategies
    - Preserves text structure
    """

    def __init__(self, redaction_char: str = "*"):
        """Initialize the PII redactor.

        Args:
            redaction_char: Character to use for redaction
        """
        self._redaction_char = redaction_char

    def redact_text(self, text: str, entities: list[PIIEntity]) -> str:
        """Redact PII entities from text.

        Args:
            text: Text to redact
            entities: PII entities to redact

        Returns:
            Redacted text
        """
        # Sort entities by start position in reverse order
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)

        redacted = list(text)
        for entity in sorted_entities:
            for i in range(entity.start, entity.end):
                redacted[i] = self._redaction_char

        result = "".join(redacted)
        logger.info("pii_redacted", count=len(entities))
        return result

    def redact_all(self, text: str) -> tuple[str, list[PIIEntity]]:
        """Detect and redact all PII in text.

        Args:
            text: Text to process

        Returns:
            Tuple of (redacted text, detected entities)
        """
        detector = PIIDetector()
        entities = detector.detect_pii(text)
        redacted = self.redact_text(text, entities)
        return redacted, entities

    def mask_entity(self, value: str, entity_type: str, visible_chars: int = 4) -> str:
        """Mask a PII entity with partial visibility.

        Args:
            value: Entity value to mask
            entity_type: Type of entity
            visible_chars: Number of characters to keep visible

        Returns:
            Masked value
        """
        if len(value) <= visible_chars:
            return self._redaction_char * len(value)

        if entity_type == "email":
            username, domain = value.split("@")
            masked_username = username[:2] + self._redaction_char * (len(username) - 2)
            return f"{masked_username}@{domain}"
        else:
            return value[:visible_chars] + self._redaction_char * (len(value) - visible_chars)
