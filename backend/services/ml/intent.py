from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import Field, ValidationError

from domain.ml.contracts import (
    ButlerMLBaseModel,
    ComplexityLevel,
    EntityReference,
    IntentAlternative,
    IntentClassifierContract,
    IntentResult,
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningResponse,
    ReasoningTier,
    ResponseFormat,
)

logger = structlog.get_logger(__name__)


class LLMIntentPayload(ButlerMLBaseModel):
    """Structured multilingual intent-classification payload."""

    label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    complexity: ComplexityLevel
    requires_tools: bool = False
    requires_memory: bool = True
    requires_approval: bool = False
    estimated_duration: int = Field(default=1, ge=0)
    requires_research: bool = False
    requires_clarification: bool = False
    multi_intent: bool = False
    entities: list[EntityReference] = Field(default_factory=list)
    alternatives: list[IntentAlternative] = Field(default_factory=list)
    calibration_metadata: dict[str, Any] = Field(default_factory=dict)


class IntentClassifier(IntentClassifierContract):
    """AI-first multilingual intent classifier.

    Design principles:
    - multilingual and language-agnostic by default
    - model-first structured classification
    - deterministic fallback rails only when runtime is unavailable or output fails validation
    - no English-only keyword routing as core logic
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

    async def classify(self, text: str) -> IntentResult:
        """Classify a user message into a structured Butler intent result."""
        normalized_text = (text or "").strip()

        if not normalized_text:
            return self._empty_input_result()

        if self._runtime is not None:
            try:
                result = await self._llm_classify(normalized_text)
                logger.info(
                    "intent_classified",
                    source="llm",
                    label=result.label,
                    confidence=result.confidence,
                    tier=result.tier.value if result.tier else None,
                    multi_intent=result.multi_intent,
                    requires_tools=result.requires_tools,
                    requires_research=result.requires_research,
                    requires_clarification=result.requires_clarification,
                )
                return result
            except Exception:
                logger.exception("intent_llm_classification_failed")

        fallback = self._default_fallback_result(normalized_text)
        logger.info(
            "intent_classified",
            source="fallback",
            label=fallback.label,
            confidence=fallback.confidence,
            tier=fallback.tier.value if fallback.tier else None,
            multi_intent=fallback.multi_intent,
            requires_tools=fallback.requires_tools,
            requires_research=fallback.requires_research,
            requires_clarification=fallback.requires_clarification,
        )
        return fallback

    async def _llm_classify(self, text: str) -> IntentResult:
        """Use structured model classification as the primary path."""
        if self._runtime is None:
            raise RuntimeError("Reasoning runtime is not configured")

        request = ReasoningRequest(
            prompt=(
                "Classify the following user message into Butler's intent schema.\n\n"
                f"User message:\n{text}\n\n"
                "Return JSON only with these fields:\n"
                "{\n"
                '  "label": "string",\n'
                '  "confidence": 0.0,\n'
                '  "complexity": "simple|complex",\n'
                '  "requires_tools": false,\n'
                '  "requires_memory": true,\n'
                '  "requires_approval": false,\n'
                '  "estimated_duration": 1,\n'
                '  "requires_research": false,\n'
                '  "requires_clarification": false,\n'
                '  "multi_intent": false,\n'
                '  "entities": [\n'
                "    {\n"
                '      "type": "string",\n'
                '      "value": "string",\n'
                '      "confidence": 0.0,\n'
                '      "metadata": {}\n'
                "    }\n"
                "  ],\n"
                '  "alternatives": [\n'
                "    {\n"
                '      "label": "string",\n'
                '      "confidence": 0.0,\n'
                '      "metadata": {}\n'
                "    }\n"
                "  ],\n"
                '  "calibration_metadata": {}\n'
                "}\n"
            ),
            system_prompt=(
                "You are Butler's multilingual intent-classification engine.\n"
                "Your job is to classify user intent across any language, mixed-language text, "
                "transliteration, or code-mixed input.\n"
                "Do not assume English.\n"
                "Do not translate unless needed internally for reasoning.\n"
                "Return only valid JSON.\n"
                "Be conservative with confidence.\n"
                "Use complexity='simple' only for straightforward low-branch requests.\n"
                "Set requires_tools=true when the user likely expects external action, retrieval, search, or tool use.\n"
                "Set requires_memory=true when prior user/session context likely matters.\n"
                "Set requires_approval=true only for risky or externally impactful actions.\n"
                "Set multi_intent=true if the message clearly contains multiple user goals.\n"
                "Set requires_research=true for exploratory, evidence-seeking, comparative, or open-ended research tasks.\n"
                "Set requires_clarification=true when the user intent is underspecified enough that execution would be risky or low quality.\n"
            ),
            max_tokens=self._max_response_tokens,
            temperature=self._model_temperature,
            response_format=ResponseFormat.JSON,
            metadata={
                "task": "intent_classification",
                "multilingual": True,
                "language_agnostic": True,
            },
        )

        response = await self._runtime.generate(
            request,
            tenant_id="default",  # P0: Intent classifier uses default tenant_id
            preferred_tier=self._default_reasoning_tier,
        )

        content = (response.content or "").strip()
        if not content:
            raise ValueError("Intent classifier returned empty content")

        structured = self._parse_payload(content)
        tier = self._response_tier(response)

        return IntentResult(
            label=self._normalize_label(structured.label),
            confidence=structured.confidence,
            complexity=structured.complexity,
            requires_tools=structured.requires_tools,
            requires_memory=structured.requires_memory,
            requires_approval=structured.requires_approval,
            estimated_duration=structured.estimated_duration,
            tier=tier,
            entities=structured.entities,
            alternatives=structured.alternatives,
            requires_clarification=structured.requires_clarification,
            multi_intent=structured.multi_intent,
            requires_research=structured.requires_research,
            calibration_metadata={
                **structured.calibration_metadata,
                "source": "llm_classifier",
                "provider_name": response.provider_name,
                "model_version": response.model_version,
                "runtime_tier": tier.value,
            },
        )

    def _parse_payload(self, content: str) -> LLMIntentPayload:
        """Parse structured classifier output robustly.

        Strategy:
        1. Direct JSON validation
        2. Strip markdown fences and retry
        3. Extract likely JSON object span and retry
        """
        candidates = self._candidate_json_strings(content)

        last_error: Exception | None = None
        for raw in candidates:
            try:
                return LLMIntentPayload.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            except ValueError as exc:
                last_error = exc

        raise ValueError(f"Invalid structured intent payload: {last_error}") from last_error

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

    def _response_tier(self, response: ReasoningResponse) -> ReasoningTier:
        raw_tier = response.metadata.get("runtime_tier")
        if isinstance(raw_tier, str):
            try:
                return ReasoningTier(raw_tier)
            except ValueError:
                pass
        return self._default_reasoning_tier

    def _normalize_label(self, label: str) -> str:
        normalized = label.strip().lower()
        return normalized or "general"

    def _empty_input_result(self) -> IntentResult:
        """Return the safest result for empty input."""
        return IntentResult(
            label="general",
            confidence=0.99,
            complexity=ComplexityLevel.SIMPLE,
            requires_tools=False,
            requires_memory=False,
            requires_approval=False,
            estimated_duration=1,
            tier=ReasoningTier.T1,
            entities=[],
            alternatives=[],
            requires_clarification=True,
            multi_intent=False,
            requires_research=False,
            calibration_metadata={"source": "empty_input_guard"},
        )

    def _default_fallback_result(self, text: str) -> IntentResult:
        """Conservative language-agnostic fallback."""
        stripped = text.strip()
        complexity = ComplexityLevel.SIMPLE if len(stripped) <= 24 else ComplexityLevel.COMPLEX

        return IntentResult(
            label="general",
            confidence=0.45,
            complexity=complexity,
            requires_tools=False,
            requires_memory=True,
            requires_approval=False,
            estimated_duration=5,
            tier=ReasoningTier.T1,
            entities=[],
            alternatives=[],
            requires_clarification=len(stripped) <= 3,
            multi_intent=False,
            requires_research=False,
            calibration_metadata={
                "source": "language_agnostic_fallback",
                "fallback_reason": "runtime_unavailable_or_invalid_output",
                "text_length": len(stripped),
            },
        )
