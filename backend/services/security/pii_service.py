"""
PII Detection and Masking Service - Privacy Compliance

Detects personally identifiable information and sensitive data.
Implements masking, redaction, and consent-based access control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PIIType(StrEnum):
    """Types of PII."""

    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    ADDRESS = "address"
    DATE_OF_BIRTH = "dob"
    PASSPORT = "passport"
    DRIVER_LICENSE = "driver_license"
    BANK_ACCOUNT = "bank_account"
    MEDICAL_RECORD = "medical_record"


@dataclass(frozen=True, slots=True)
class PIIMatch:
    """PII detection match."""

    pii_type: PIIType
    matched_text: str
    start_index: int
    end_index: int
    confidence: float


@dataclass(frozen=True, slots=True)
class PIIScanResult:
    """Result of PII scan."""

    has_pii: bool
    matches: list[PIIMatch]
    pii_types_found: set[PIIType]
    risk_score: float  # 0.0 to 1.0


class PIIService:
    """
    PII detection and masking service.

    Features:
    - Regex-based PII detection
    - Multiple masking strategies
    - Risk scoring
    - Consent-aware access control
    """

    def __init__(self) -> None:
        """Initialize PII service."""
        self._patterns = self._build_patterns()

    def _build_patterns(self) -> dict[PIIType, re.Pattern]:
        """Build regex patterns for PII detection."""
        return {
            PIIType.EMAIL: re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                re.IGNORECASE,
            ),
            PIIType.PHONE: re.compile(
                r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b",
            ),
            PIIType.SSN: re.compile(
                r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b",
            ),
            PIIType.CREDIT_CARD: re.compile(
                r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|(?:2131|1800|35\d{3})\d{11})\b",
            ),
            PIIType.IP_ADDRESS: re.compile(
                r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            ),
            PIIType.DATE_OF_BIRTH: re.compile(
                r"\b(?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12][0-9]|3[01])[-/](?:19|20)\d{2}\b",
            ),
            PIIType.PASSPORT: re.compile(
                r"\b[A-Za-z]{1,2}\d{6,9}\b",  # Simplified passport pattern
            ),
            PIIType.BANK_ACCOUNT: re.compile(
                r"\b\d{8,17}\b",  # Simplified bank account pattern
            ),
        }

    def scan_text(self, text: str) -> PIIScanResult:
        """
        Scan text for PII.

        Args:
            text: Text to scan

        Returns:
            PII scan result
        """
        matches = []
        pii_types_found = set()

        for pii_type, pattern in self._patterns.items():
            for match in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        pii_type=pii_type,
                        matched_text=match.group(),
                        start_index=match.start(),
                        end_index=match.end(),
                        confidence=0.8,  # Base confidence for regex match
                    )
                )
                pii_types_found.add(pii_type)

        # Calculate risk score based on PII types found
        risk_weights = {
            PIIType.SSN: 0.9,
            PIIType.CREDIT_CARD: 0.9,
            PIIType.BANK_ACCOUNT: 0.85,
            PIIType.MEDICAL_RECORD: 0.9,
            PIIType.PASSPORT: 0.85,
            PIIType.EMAIL: 0.3,
            PIIType.PHONE: 0.4,
            PIIType.IP_ADDRESS: 0.2,
            PIIType.NAME: 0.2,
            PIIType.ADDRESS: 0.3,
            PIIType.DATE_OF_BIRTH: 0.5,
            PIIType.DRIVER_LICENSE: 0.8,
        }

        risk_score = 0.0
        for pii_type in pii_types_found:
            risk_score = max(risk_score, risk_weights.get(pii_type, 0.5))

        # Increase risk score if multiple PII types found
        if len(pii_types_found) > 1:
            risk_score = min(1.0, risk_score + 0.2)

        return PIIScanResult(
            has_pii=len(matches) > 0,
            matches=matches,
            pii_types_found=pii_types_found,
            risk_score=risk_score,
        )

    def mask_text(
        self,
        text: str,
        mask_char: str = "*",
        preserve_length: bool = True,
    ) -> str:
        """
        Mask all PII in text.

        Args:
            text: Text to mask
            mask_char: Character to use for masking
            preserve_length: Whether to preserve original length

        Returns:
            Masked text
        """
        # First scan for PII
        scan_result = self.scan_text(text)

        if not scan_result.has_pii:
            return text

        # Sort matches by start index in reverse order to avoid index shifting
        sorted_matches = sorted(scan_result.matches, key=lambda m: m.start_index, reverse=True)

        masked_text = text
        for match in sorted_matches:
            if preserve_length:
                masked_text = (
                    masked_text[: match.start_index]
                    + mask_char * (match.end_index - match.start_index)
                    + masked_text[match.end_index :]
                )
            else:
                masked_text = (
                    masked_text[: match.start_index]
                    + f"[{match.pii_type} REDACTED]"
                    + masked_text[match.end_index :]
                )

        return masked_text

    def mask_pii_type(
        self,
        text: str,
        pii_type: PIIType,
        mask_char: str = "*",
    ) -> str:
        """
        Mask specific PII type in text.

        Args:
            text: Text to mask
            pii_type: PII type to mask
            mask_char: Character to use for masking

        Returns:
            Masked text
        """
        pattern = self._patterns.get(pii_type)
        if not pattern:
            return text

        return pattern.sub(mask_char * 8, text)  # Replace with 8 mask chars

    def redact_json(
        self,
        data: dict[str, Any],
        sensitive_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Redact sensitive fields in JSON data.

        Args:
            data: JSON data to redact
            sensitive_fields: Field names to redact (default: common sensitive fields)

        Returns:
            Redacted JSON data
        """
        if sensitive_fields is None:
            sensitive_fields = {
                "password",
                "token",
                "secret",
                "api_key",
                "access_key",
                "secret_key",
                "ssn",
                "social_security",
                "credit_card",
                "bank_account",
                "medical_record",
                "passport",
                "driver_license",
            }

        redacted = {}
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self.redact_json(value, sensitive_fields)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact_json(item, sensitive_fields) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value

        return redacted

    def get_risk_level(self, risk_score: float) -> str:
        """
        Get risk level from risk score.

        Args:
            risk_score: Risk score (0.0 to 1.0)

        Returns:
            Risk level (low, medium, high, critical)
        """
        if risk_score >= 0.8:
            return "critical"
        if risk_score >= 0.6:
            return "high"
        if risk_score >= 0.3:
            return "medium"
        return "low"


class ConsentService:
    """
    Consent management service for privacy compliance.

    Features:
    - Consent tracking
    - Consent revocation
    - Data retention based on consent
    - PII access control
    """

    def __init__(self, redis_client) -> None:
        """Initialize consent service."""
        self._redis = redis_client

    def _consent_key(self, user_id: str) -> str:
        """Generate Redis key for consent data."""
        return f"consent:{user_id}"

    async def grant_consent(
        self,
        user_id: str,
        consent_type: str,
        granted: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Grant or revoke consent for user.

        Args:
            user_id: User UUID
            consent_type: Type of consent (e.g., "data_processing", "analytics")
            granted: Whether consent is granted
            metadata: Additional consent metadata
        """
        import json

        consent_data = {
            "user_id": user_id,
            "consent_type": consent_type,
            "granted": granted,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        await self._redis.hset(
            self._consent_key(user_id),
            mapping={
                consent_type: json.dumps(consent_data),
            },
        )

        logger.info(
            "consent_granted",
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
        )

    async def check_consent(
        self,
        user_id: str,
        consent_type: str,
    ) -> bool:
        """
        Check if user has granted consent.

        Args:
            user_id: User UUID
            consent_type: Type of consent to check

        Returns:
            True if consent granted, False otherwise
        """
        consent_data = await self._redis.hget(self._consent_key(user_id), consent_type)

        if not consent_data:
            # Default to no consent if not explicitly granted
            return False

        import json

        try:
            data = json.loads(consent_data.decode())
            return data.get("granted", False)
        except Exception:
            return False

    async def revoke_consent(
        self,
        user_id: str,
        consent_type: str,
    ) -> None:
        """
        Revoke consent for user.

        Args:
            user_id: User UUID
            consent_type: Type of consent to revoke
        """
        await self.grant_consent(user_id, consent_type, granted=False)

        logger.info(
            "consent_revoked",
            user_id=user_id,
            consent_type=consent_type,
        )

    async def get_all_consents(self, user_id: str) -> dict[str, Any]:
        """
        Get all consents for user.

        Args:
            user_id: User UUID

        Returns:
            Dictionary of consent types to consent data
        """
        consent_data = await self._redis.hgetall(self._consent_key(user_id))

        result = {}
        import json

        for key, value in consent_data.items():
            try:
                result[key.decode()] = json.loads(value.decode())
            except Exception:
                result[key.decode()] = {"granted": False}

        return result

    async def can_process_data(
        self,
        user_id: str,
        data_type: str,
    ) -> bool:
        """
        Check if data can be processed based on consent.

        Args:
            user_id: User UUID
            data_type: Type of data to process

        Returns:
            True if processing allowed, False otherwise
        """
        # Check specific consent for data type
        if await self.check_consent(user_id, f"process_{data_type}"):
            return True

        # Check general data processing consent
        return bool(await self.check_consent(user_id, "data_processing"))

    async def scrub_pii(
        self,
        user_id: str,
        text: str,
        pii_service: PIIService,
    ) -> str:
        """
        Scrub PII from text if user has not consented.

        Args:
            user_id: User UUID
            text: Text to scrub
            pii_service: PII service for detection

        Returns:
            Scrubbed text
        """
        # Check if user has consented to PII processing
        if await self.check_consent(user_id, "pii_processing"):
            return text

        # Scrub PII if no consent
        return pii_service.mask_text(text)
