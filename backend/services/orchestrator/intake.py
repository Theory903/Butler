from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

from core.envelope import ButlerEnvelope
from domain.ml.contracts import IntentClassifierContract, IntentResult


class IntakeResult(BaseModel):
    label: str
    intent: str
    confidence: float
    complexity: str
    mode: str
    requires_tools: bool
    requires_memory: bool
    environment_block: Optional[str] = None   # Injected ambient context for prompt


class IntakeProcessor:
    """Phase 1: Receive envelope → classify intent → inject environment → select mode.

    v3.1: Environment context is optionally injected when EnvironmentService
    is wired. The resulting `environment_block` is passed downstream to the
    Orchestrator for inclusion in the system prompt.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifierContract,
        environment_service: object | None = None,   # EnvironmentService (optional)
    ) -> None:
        self._classifier = intent_classifier
        self._env_service = environment_service

    async def process(self, envelope: ButlerEnvelope) -> IntakeResult:
        # 1. Classify intent
        intent: IntentResult = await self._classifier.classify(envelope.message)

        # 2. Ambient environment context (best-effort, never fails hard)
        env_block: Optional[str] = None
        if self._env_service:
            try:
                snapshot = await self._env_service.get_snapshot(
                    account_id=envelope.account_id,
                    device_id=getattr(envelope, "device_id", "unknown"),
                )
                env_block = snapshot.to_prompt_block()
            except Exception:
                pass  # Never break intake because env is optional grounding

        # 3. Select execution mode
        mode = self._select_mode(intent)

        return IntakeResult(
            label=intent.label,
            intent=intent.label,
            confidence=intent.confidence,
            complexity=intent.complexity,
            mode=mode,
            requires_tools=intent.requires_tools,
            requires_memory=intent.requires_memory,
            environment_block=env_block,
        )

    def _select_mode(self, intent: IntentResult) -> str:
        """Route to execution mode based on intent analysis.

        Macro    — LLM-driven, complex, multi-step.
        Routine  — Template-based, deterministic.
        Durable  — Long-running, needs checkpointed persistence.
        Research — Deep search + evidence gathering.
        """
        label = intent.label.lower()
        if getattr(intent, "requires_research", False) or "search" in label or "research" in label:
            return "research"
        elif intent.complexity == "simple" and not intent.requires_tools:
            return "routine"
        elif intent.requires_approval or intent.estimated_duration > 30:
            return "durable"
        else:
            return "macro"
