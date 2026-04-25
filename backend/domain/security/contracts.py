"""domain/security/contracts.py — Security service abstractions.

Keeps OrchestratorService and any consumer decoupled from the
concrete RedactionService and ContentGuard implementations.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from domain.base import DomainService


class IRedactionService(DomainService):
    """Abstraction over services.security.redaction.RedactionService."""

    @abstractmethod
    def redact(self, text: str) -> tuple[str, dict[str, list[str]]]:
        """Return (redacted_text, redaction_map) with PII replaced by placeholder tokens."""

    @abstractmethod
    def restore(self, text: str, redaction_map: dict[str, list[str]]) -> str:
        """Restore placeholder tokens back to original PII values."""

    @abstractmethod
    def redact_dict(self, data: dict) -> dict:
        """Recursively redact all string values in a dict."""

    @abstractmethod
    def has_pii(self, text: str) -> bool:
        """Return True if the text contains detectable PII."""


class IContentGuard(DomainService):
    """Abstraction over services.security.safety.ContentGuard."""

    @abstractmethod
    async def check(self, text: str) -> dict[str, Any]:
        """Return {'safe': bool, 'reason': str} safety classification."""

    @abstractmethod
    async def is_safe(self, text: str, context: dict | None = None) -> bool:
        """Return True if the content passes all safety checks."""

    @abstractmethod
    async def classify(self, text: str) -> dict[str, Any]:
        """Return a detailed safety classification result dict."""
