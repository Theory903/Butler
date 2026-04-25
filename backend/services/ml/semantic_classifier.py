"""Semantic Classification Service — Multilingual, Model-First Classification.

Replaces deterministic keyword/phrase matching with AI-driven semantic understanding.
Supports safety detection, risk classification, and intent analysis across languages.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError

from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningTier,
    ResponseFormat,
)

logger = structlog.get_logger(__name__)


class RiskLevel(StrEnum):
    """Risk classification levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyCategory(StrEnum):
    """Safety violation categories."""
    TOXICITY = "toxicity"
    HATE_SPEECH = "hate_speech"
    SELF_HARM = "self_harm"
    SEXUAL_CONTENT = "sexual_content"
    VIOLENCE = "violence"
    PII = "pii"
    NONE = "none"


@dataclass
class SafetyClassification:
    """Result of safety classification."""
    is_safe: bool
    risk_level: RiskLevel
    categories: list[SafetyCategory]
    confidence: float
    reasoning: str
    language: str
    capability_required: str


@dataclass
class RiskClassification:
    """Result of risk classification for tool operations."""
    risk_level: RiskLevel
    requires_approval: bool
    requires_sandbox: bool
    confidence: float
    reasoning: str
    language: str
    capability_required: str


class SafetyClassificationRequest(BaseModel):
    """Structured request for safety classification."""
    text: str = Field(min_length=1)
    context: str | None = None


class SafetyClassificationResponse(BaseModel):
    """Structured response from safety classifier."""
    is_safe: bool = Field(description="Whether the text is safe")
    risk_level: str = Field(description="Risk level: low, medium, high, critical")
    categories: list[str] = Field(description="List of safety category violations")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str = Field(description="Brief explanation of the classification")
    language: str = Field(description="Detected language of input")
    # Capability required for handling this request (deterministic enforcement)
    capability_required: str = Field(description="Capability identifier for policy enforcement")


class RiskClassificationRequest(BaseModel):
    """Structured request for risk classification."""
    tool_name: str = Field(min_length=1)
    params: dict[str, Any] | None = None
    description: str | None = None


class RiskClassificationResponse(BaseModel):
    """Structured response from risk classifier."""
    risk_level: str = Field(description="Risk level: low, medium, high, critical")
    requires_approval: bool = Field(description="Whether human approval is required")
    requires_sandbox: bool = Field(description="Whether sandboxed execution is required")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    reasoning: str = Field(description="Brief explanation of the classification")
    language: str = Field(description="Detected language of input")
    # Capability required for handling this request (deterministic enforcement)
    capability_required: str = Field(description="Capability identifier for policy enforcement")


class SemanticClassifier:
    """Multilingual, model-first semantic classification service.

    Design principles:
    - Semantic understanding over keyword matching
    - Works across languages, code-mixed input, transliteration
    - LLM-based primary path with fallback
    - Structured JSON output with validation
    """

    def __init__(
        self,
        runtime: IReasoningRuntime | None = None,
        *,
        default_reasoning_tier: ReasoningTier = ReasoningTier.T2,
        max_response_tokens: int = 800,
        model_temperature: float = 0.1,
    ) -> None:
        self._runtime = runtime
        self._default_reasoning_tier = default_reasoning_tier
        self._max_response_tokens = max_response_tokens
        self._model_temperature = model_temperature

    async def classify_safety(self, text: str, context: str | None = None) -> SafetyClassification:
        """Classify text for safety violations using semantic understanding.

        Args:
            text: Input text to classify
            context: Optional context for better classification

        Returns:
            SafetyClassification with risk level, categories, and reasoning
        """
        start_time = time.time()
        text_hash = hashlib.sha256(text.encode()).hexdigest()

        logger.info(
            "safety_classification_started",
            input_hash=text_hash,
            text_length=len(text),
        )

        if self._runtime is not None:
            try:
                result = await self._llm_safety_classify(text, context)
                latency = time.time() - start_time

                logger.info(
                    "safety_classified",
                    source="llm",
                    input_hash=text_hash,
                    is_safe=result.is_safe,
                    risk_level=result.risk_level.value,
                    categories=[c.value for c in result.categories],
                    confidence=result.confidence,
                    language=result.language,
                    capability_required=result.capability_required,
                    latency_seconds=latency,
                )
                return result
            except Exception as exc:
                latency = time.time() - start_time
                logger.warning(
                    "safety_llm_classification_failed",
                    input_hash=text_hash,
                    error=str(exc),
                    latency_seconds=latency,
                )

        # Conservative fallback
        latency = time.time() - start_time
        logger.info(
            "safety_fallback_conservative",
            input_hash=text_hash,
            latency_seconds=latency,
        )
        return self._default_safety_fallback(text)

    async def _llm_safety_classify(
        self, text: str, context: str | None = None
    ) -> SafetyClassification:
        """Use LLM for semantic safety classification."""
        if self._runtime is None:
            raise RuntimeError("Reasoning runtime is not configured")

        context_str = f"\nContext: {context}" if context else ""
        request = ReasoningRequest(
            prompt=(
                "Classify the following text for safety violations.\n\n"
                f"Text:\n{text}{context_str}\n\n"
                "Return JSON only with these fields:\n"
                "{\n"
                '  "is_safe": true,\n'
                '  "risk_level": "low|medium|high|critical",\n'
                '  "categories": ["toxicity", "hate_speech", "self_harm", "sexual_content", "violence", "pii", "none"],\n'
                '  "confidence": 0.0,\n'
                '  "reasoning": "brief explanation",\n'
                '  "language": "detected language or mixed",\n'
                '  "capability_required": "capability identifier for policy enforcement"\n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual safety-classification engine.\n"
                "Your job is to detect safety violations across any language, mixed-language text, "
                "transliteration, or code-mixed input.\n"
                "Do not assume English.\n"
                "Do not translate unless needed internally for reasoning.\n"
                "Return only valid JSON.\n"
                "Be conservative with confidence.\n"
                "Classify risk based on semantic meaning, not literal words.\n"
                "Consider cultural context and indirect phrasing.\n"
                "Set is_safe=true only when no safety violations are detected.\n"
                "Use categories to specify the type of violation.\n"
                "Set risk_level based on severity of violation.\n"
            ),
            max_tokens=self._max_response_tokens,
            temperature=self._model_temperature,
            response_format=ResponseFormat.JSON,
            metadata={
                "task": "safety_classification",
                "multilingual": True,
                "language_agnostic": True,
            },
        )

        response = await self._runtime.generate(
            request,
            tenant_id="default",  # P0: Safety classifier uses default tenant_id
            preferred_tier=self._default_reasoning_tier,
        )

        content = (response.content or "").strip()
        if not content:
            raise ValueError("Safety classifier returned empty content")

        structured = self._parse_safety_response(content)

        return SafetyClassification(
            is_safe=structured.is_safe,
            risk_level=RiskLevel(structured.risk_level),
            categories=[SafetyCategory(c) for c in structured.categories],
            confidence=structured.confidence,
            reasoning=structured.reasoning,
            language=structured.language,
            capability_required=structured.capability_required,
        )

    def _parse_safety_response(self, content: str) -> SafetyClassificationResponse:
        """Parse structured safety classifier output robustly."""
        candidates = self._candidate_json_strings(content)

        last_error: Exception | None = None
        for raw in candidates:
            try:
                return SafetyClassificationResponse.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            except ValueError as exc:
                last_error = exc

        raise ValueError(f"Invalid safety classification payload: {last_error}") from last_error

    def _default_safety_fallback(self, text: str) -> SafetyClassification:
        """Conservative fallback when LLM is unavailable."""
        return SafetyClassification(
            is_safe=True,
            risk_level=RiskLevel.LOW,
            categories=[],
            confidence=0.5,
            reasoning="LLM classifier unavailable - conservative safe default",
            language="unknown",
            capability_required="general.query",
        )

    async def classify_risk(
        self, tool_name: str, params: dict[str, Any] | None = None, description: str | None = None
    ) -> RiskClassification:
        """Classify tool operation risk using semantic understanding.

        Args:
            tool_name: Name of the tool being executed
            params: Optional parameters passed to the tool
            description: Optional description of the tool

        Returns:
            RiskClassification with risk level, approval requirements, and reasoning
        """
        start_time = time.time()
        tool_hash = hashlib.sha256(f"{tool_name}{str(params)}".encode()).hexdigest()

        logger.info(
            "risk_classification_started",
            tool_hash=tool_hash,
            tool_name=tool_name,
        )

        if self._runtime is not None:
            try:
                result = await self._llm_risk_classify(tool_name, params, description)
                latency = time.time() - start_time

                logger.info(
                    "risk_classified",
                    source="llm",
                    tool_hash=tool_hash,
                    tool_name=tool_name,
                    risk_level=result.risk_level.value,
                    requires_approval=result.requires_approval,
                    requires_sandbox=result.requires_sandbox,
                    confidence=result.confidence,
                    language=result.language,
                    capability_required=result.capability_required,
                    latency_seconds=latency,
                )
                return result
            except Exception:
                logger.exception("risk_llm_classification_failed")

        # Conservative fallback
        return self._default_risk_fallback(tool_name, params)

    async def _llm_risk_classify(
        self, tool_name: str, params: dict[str, Any] | None = None, description: str | None = None
    ) -> RiskClassification:
        """Use LLM for semantic risk classification."""
        if self._runtime is None:
            raise RuntimeError("Reasoning runtime is not configured")

        params_str = f"\nParameters: {json.dumps(params, default=str)}" if params else ""
        desc_str = f"\nDescription: {description}" if description else ""
        request = ReasoningRequest(
            prompt=(
                "Classify the risk level of the following tool operation.\n\n"
                f"Tool name:\n{tool_name}{params_str}{desc_str}\n\n"
                "Return JSON only with these fields:\n"
                "{\n"
                '  "risk_level": "low|medium|high|critical",\n'
                '  "requires_approval": true,\n'
                '  "requires_sandbox": false,\n'
                '  "confidence": 0.0,\n'
                '  "reasoning": "brief explanation",\n'
                '  "language": "detected language or mixed",\n'
                '  "capability_required": "capability identifier for policy enforcement"\n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual risk-classification engine.\n"
                "Your job is to assess tool operation risk across any language.\n"
                "Do not assume English.\n"
                "Do not translate unless needed internally for reasoning.\n"
                "Return only valid JSON.\n"
                "Be conservative with confidence.\n"
                "Classify risk based on semantic meaning of the operation, not literal words.\n"
                "Set requires_approval=true for critical, financial, physical, or destructive operations.\n"
                "Set requires_sandbox=true for operations that affect external systems or devices.\n"
                "Consider the potential impact of the operation, not just the name.\n"
            ),
            max_tokens=self._max_response_tokens,
            temperature=self._model_temperature,
            response_format=ResponseFormat.JSON,
            metadata={
                "task": "risk_classification",
                "multilingual": True,
                "language_agnostic": True,
            },
        )

        response = await self._runtime.generate(
            request,
            tenant_id="default",  # P0: Safety classifier uses default tenant_id
            preferred_tier=self._default_reasoning_tier,
        )

        content = (response.content or "").strip()
        if not content:
            raise ValueError("Risk classifier returned empty content")

        structured = self._parse_risk_response(content)

        return RiskClassification(
            risk_level=RiskLevel(structured.risk_level),
            requires_approval=structured.requires_approval,
            requires_sandbox=structured.requires_sandbox,
            confidence=structured.confidence,
            reasoning=structured.reasoning,
            language=structured.language,
            capability_required=structured.capability_required,
        )

    def _parse_risk_response(self, content: str) -> RiskClassificationResponse:
        """Parse structured risk classifier output robustly."""
        candidates = self._candidate_json_strings(content)

        last_error: Exception | None = None
        for raw in candidates:
            try:
                return RiskClassificationResponse.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            except ValueError as exc:
                last_error = exc

        raise ValueError(f"Invalid risk classification payload: {last_error}") from last_error

    def _default_risk_fallback(
        self, tool_name: str, params: dict[str, Any] | None = None
    ) -> RiskClassification:
        """Conservative fallback when LLM is unavailable."""
        return RiskClassification(
            risk_level=RiskLevel.MEDIUM,
            requires_approval=False,
            requires_sandbox=False,
            confidence=0.5,
            reasoning="LLM classifier unavailable - conservative medium risk default",
            language="unknown",
            capability_required="general.query",
        )

    def _candidate_json_strings(self, content: str) -> list[str]:
        """Generate plausible JSON candidate strings from model output."""
        raw = content.strip()
        candidates: list[str] = []

        if raw:
            candidates.append(raw)

        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) >= 3:
                unfenced = "\n".join(lines[1:-1]).strip()
                if unfenced:
                    candidates.append(unfenced)

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            extracted = raw[start : end + 1].strip()
            if extracted:
                candidates.append(extracted)

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)

        return unique
