from __future__ import annotations

from typing import Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

from core.envelope import ButlerEnvelope
from domain.ml.contracts import IntentClassifierContract, IntentResult

logger = structlog.get_logger(__name__)


class EnvironmentSnapshotContract(Protocol):
    """Contract for environment snapshots that can be converted to prompt context."""

    def to_prompt_block(self) -> str:
        """Render the environment snapshot into prompt-safe text."""


class EnvironmentServiceContract(Protocol):
    """Contract for optional ambient environment providers."""

    async def get_snapshot(
        self,
        *,
        account_id: str,
        device_id: str,
    ) -> EnvironmentSnapshotContract:
        """Return an environment snapshot for the current account/device."""


class ModeRouterContract(Protocol):
    """Contract for mode routing decisions."""

    async def select_mode(
        self,
        *,
        intent: IntentResult,
        envelope: ButlerEnvelope,
        environment_block: str | None,
    ) -> str:
        """Return the execution mode for the request."""


class IntakeResult(BaseModel):
    """Normalized intake output passed into planning/orchestration."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    confidence: float
    complexity: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    requires_tools: bool
    requires_memory: bool
    environment_block: str | None = None


class DeterministicModeRouter:
    """LLM-driven mode router.

    Delegates mode selection to the execution backend (Hermes agent).
    This ensures the LLM decides what to do, not hardcoded rules.
    """

    async def select_mode(
        self,
        *,
        intent: IntentResult,
        envelope: ButlerEnvelope,
        environment_block: str | None,
    ) -> str:
        return "agentic"


class IntakeProcessor:
    """Receive envelope, classify intent, enrich context, and select execution mode."""

    def __init__(
        self,
        *,
        intent_classifier: IntentClassifierContract,
        environment_service: EnvironmentServiceContract | None = None,
        mode_router: ModeRouterContract | None = None,
    ) -> None:
        self._classifier = intent_classifier
        self._env_service = environment_service
        self._mode_router = mode_router or DeterministicModeRouter()

    async def process(self, envelope: ButlerEnvelope) -> IntakeResult:
        """Process one incoming envelope into normalized intake output."""
        intent = await self._classifier.classify(envelope.message)
        environment_block = await self._build_environment_block(envelope)
        mode = await self._mode_router.select_mode(
            intent=intent,
            envelope=envelope,
            environment_block=environment_block,
        )

        result = IntakeResult(
            label=intent.label,
            intent=self._normalize_intent(intent),
            confidence=float(intent.confidence),
            complexity=str(intent.complexity),
            mode=mode,
            requires_tools=bool(intent.requires_tools),
            requires_memory=bool(intent.requires_memory),
            environment_block=environment_block,
        )

        logger.info(
            "intake_processed",
            label=result.label,
            intent=result.intent,
            confidence=result.confidence,
            complexity=result.complexity,
            mode=result.mode,
            requires_tools=result.requires_tools,
            requires_memory=result.requires_memory,
            has_environment=bool(result.environment_block),
        )

        return result

    async def _build_environment_block(self, envelope: ButlerEnvelope) -> str | None:
        """Build optional environment grounding block.

        Environment grounding is best-effort only. Failures are logged and do
        not block intake.
        """
        if self._env_service is None:
            return None

        device_id = getattr(envelope, "device_id", None) or "unknown"

        try:
            snapshot = await self._env_service.get_snapshot(
                account_id=envelope.account_id,
                device_id=device_id,
            )
            block = snapshot.to_prompt_block()
            return block.strip() or None
        except Exception:
            logger.exception(
                "intake_environment_snapshot_failed",
                account_id=envelope.account_id,
                device_id=device_id,
            )
            return None

    def _normalize_intent(self, intent: IntentResult) -> str:
        """Normalize classifier output into a planner-safe intent string."""
        label = str(intent.label or "").strip().lower()
        return label or "unknown"
