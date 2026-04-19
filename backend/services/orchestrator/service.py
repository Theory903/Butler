import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.base_service import ButlerBaseService
from core.envelope import ButlerEnvelope
from domain.events.schemas import ButlerEvent, StreamFinalEvent, StreamTokenEvent
from domain.memory.contracts import IColdStore, IMemoryWriteStore, MemoryServiceContract
from domain.orchestrator.contracts import OrchestratorResult, OrchestratorServiceContract
from domain.orchestrator.exceptions import OrchestratorErrors
from domain.orchestrator.models import ApprovalRequest, Task, Workflow
from domain.orchestrator.runtime_kernel import RuntimeKernel
from domain.orchestrator.state import TaskStateMachine
from domain.search.contracts import ISearchService
from domain.security.contracts import IContentGuard, IRedactionService
from domain.tools.contracts import ToolsServiceContract
from services.memory.session_store import ButlerSessionStore
from services.orchestrator.blender import BlenderSignal, ButlerBlender
from services.orchestrator.executor import DurableExecutor
from services.orchestrator.intake import IntakeProcessor
from services.orchestrator.planner import PlanEngine

logger = structlog.get_logger(__name__)

class OrchestratorService(ButlerBaseService, OrchestratorServiceContract):
    """Butler's federated intelligence supervisor (v3.1).

    Depends only on domain contracts — no concrete service imports.
    All concrete wiring lives in core/deps.py.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        intake_proc: IntakeProcessor,
        planner: PlanEngine,
        executor: DurableExecutor,
        kernel: RuntimeKernel,
        blender: ButlerBlender,
        memory_store: IMemoryWriteStore | None = None,
        cold_store: IColdStore | None = None,
        memory_service: MemoryServiceContract | None = None,  # For context compression
        tools_service: ToolsServiceContract | None = None,
        answering_engine: ISearchService | None = None,
        smart_router: Any | None = None,
        redaction_service: IRedactionService | None = None,
        content_guard: IContentGuard | None = None,
        config: ButlerBaseConfig | None = None,
    ):
        if not config:
            from pydantic import SecretStr

            from core.base_config import ButlerBaseConfig
            config = ButlerBaseConfig(
                SERVICE_NAME="orchestrator",
                BUTLER_INTERNAL_KEY=SecretStr("dev-key-mock")
            )
        super().__init__(config=config)
        self._db = db
        self._redis = redis
        self._intake = intake_proc
        self._planner = planner
        self._executor = executor
        self._kernel = kernel
        self._blender = blender
        self._memory_store = memory_store
        self._cold_store = cold_store
        self._memory = memory_service
        self._tools = tools_service
        self._answering_engine = answering_engine
        self._smart_router = smart_router
        # Security: lazily fall back to concrete impls only if no contract injected
        self._redactor: IRedactionService | Any = redaction_service
        self._guard: IContentGuard | Any = content_guard

    async def on_startup(self) -> None:
        """Standard startup logic for the Orchestrator service."""
        logger.info("orchestrator_service_startup_complete")

    async def on_shutdown(self) -> None:
        """Standard shutdown logic for the Orchestrator service."""
        logger.info("orchestrator_service_shutdown_complete")

    def _make_session_store(self, session_id: str, account_id: str) -> ButlerSessionStore | None:
        if not self._memory_store:
            return None
        return ButlerSessionStore(
            session_id=session_id,
            account_id=account_id,
            memory_store=self._memory_store,
            redis=self._redis,
            cold_store=self._cold_store,
        )

    async def _check_safety(self, text: str) -> dict[str, Any]:
        """Run content safety check. Defaults to safe=True if no guard injected."""
        if self._guard is None:
            return {"safe": True, "reason": "no_guard"}
        return await self._guard.check(text)

    def _redact_input(self, text: str):
        """Redact PII from input. Returns (text, {}) if no redactor injected."""
        if self._redactor is None:
            return text, {}
        return self._redactor.redact(text)

    def _restore_output(self, text: str, redaction_map: dict) -> str:
        """Restore PII placeholders. No-op if no redactor injected."""
        if self._redactor is None or not redaction_map:
            return text
        return self._redactor.restore(text, redaction_map)

    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        """Standard intake pipeline with security guardrails."""

        # 1. Input Safety Check
        safety = await self._check_safety(envelope.message)
        if not safety["safe"]:
            return OrchestratorResult(
                content=f"Request blocked by safety policy: {safety['reason']}",
                actions=[],
                workflow_id=str(uuid.uuid4())
            )

        # 2. Input Redaction (PII Protection)
        redacted_msg, redaction_map = self._redact_input(envelope.message)
        envelope.message = redacted_msg

        store = self._make_session_store(envelope.session_id, envelope.account_id)

        # 3. Process Signals
        intake_result = await self._intake.process(envelope)

        # 4. Smart Routing
        if self._smart_router:
            from services.ml.smart_router import RouterRequest
            routing_req = RouterRequest(
                intent=intake_result,
                message=envelope.message,
                context_token_count=0,
            )
            routing_decision = self._smart_router.route(routing_req)
            if routing_decision.tier.value < 2:
                return OrchestratorResult(
                    content=intake_result.label,
                    actions=[],
                    workflow_id=str(uuid.uuid4())
                )

        # 5. Blend & Plan
        signal = BlenderSignal(
            user_id=envelope.account_id,
            session_id=envelope.session_id,
            query=envelope.message,
            context={"intent": intake_result.intent, "mode": intake_result.mode}
        )
        candidates = await self._blender.blend(signal)

        context_str = "\n".join([f"- [{c.source}] {c.content}" for c in candidates])
        augmented_prompt = f"Context:\n{context_str}\n\nUser request: {envelope.message}"

        workflow = Workflow(
            id=uuid.uuid4(),
            account_id=uuid.UUID(envelope.account_id),
            session_id=envelope.session_id,
            intent=intake_result.intent,
            mode=intake_result.mode,
            context_snapshot={"blender_count": len(candidates), "redacted": len(redaction_map) > 0}
        )
        self._db.add(workflow)

        plan = await self._planner.create_plan(intent=intake_result.intent, context={"prompt": augmented_prompt})
        result = await self._executor.execute_workflow(workflow, plan)

        # 6. Post-process: Output Safety & Restore
        if result.content:
            out_safety = await self._check_safety(result.content)
            if not out_safety["safe"]:
                result.content = "[Blocked by output safety protocol]"
            else:
                result.content = self._restore_output(result.content, redaction_map)

        await self._db.commit()

        # 7. Persistence
        if store and result.content:
            await store.append_turn(role="assistant", content=result.content)
            await store.flush_to_long_term(content=result.content, memory_type="episode")
            # Trigger context compression if history gets deep
            await self._trigger_compression(envelope.account_id, envelope.session_id, store)

        return OrchestratorResult(
            workflow_id=str(workflow.id),
            content=result.content,
            actions=result.actions,
            input_tokens=getattr(result, "input_tokens", 0),
            output_tokens=getattr(result, "output_tokens", 0),
            duration_ms=getattr(result, "duration_ms", 0),
        )

    async def intake_streaming(
        self, envelope: ButlerEnvelope
    ) -> AsyncGenerator[ButlerEvent, None]:
        """Streaming pipeline with security guardrails."""

        # 1. Input Safety Check
        safety = await self._check_safety(envelope.message)
        if not safety["safe"]:
            yield StreamFinalEvent(payload={"content": f"Safety Block: {safety['reason']}", "session_id": envelope.session_id})
            return

        # 2. Redact
        redacted_msg, redaction_map = self._redact_input(envelope.message)
        envelope.message = redacted_msg

        store = self._make_session_store(envelope.session_id, envelope.account_id)
        if store:
            await store.append_turn(role="user", content=envelope.message)

        # 3. Classify & Route
        intake_result = await self._intake.process(envelope)

        if self._smart_router:
            from services.ml.smart_router import RouterRequest
            routing_req = RouterRequest(
                intent=intake_result,
                message=envelope.message,
                context_token_count=0,
            )
            routing_decision = self._smart_router.route(routing_req)
            if routing_decision.tier.value < 2:
                yield StreamFinalEvent(payload={"content": intake_result.label, "session_id": envelope.session_id})
                return

        # 4. Workflow & Plan
        workflow = Workflow(
            account_id=uuid.UUID(envelope.account_id),
            session_id=envelope.session_id,
            intent=intake_result.intent,
            mode=intake_result.mode,
            context_snapshot={"message": envelope.message, "channel": envelope.channel},
        )
        self._db.add(workflow)
        await self._db.flush()

        plan = await self._planner.create_plan(intent=intake_result.intent, context=workflow.context_snapshot)
        workflow.plan_schema = plan.to_dict()
        await self._db.commit()

        # 5. Blend
        signal = BlenderSignal(
            user_id=envelope.account_id,
            session_id=envelope.session_id,
            query=envelope.message,
            context={"intent": intake_result.intent, "mode": intake_result.mode, "channel": envelope.channel}
        )
        candidates = await self._blender.blend(signal)

        if store:
            context_pack = await store.get_context(query=envelope.message)
            messages: list[dict] = [
                {"role": t.get("role", "user"), "content": t.get("content", "")}
                for t in context_pack.session_history
            ]
        else:
            messages = []

        if candidates:
            context_str = "\n".join([f"- [{c.source}] {c.content}" for c in candidates])
            messages.append({"role": "system", "content": f"Context candidates:\n{context_str}"})

        messages.append({"role": "user", "content": envelope.message})

        # 6. Stream with Post-processing (Buffered for restoration)
        final_content_parts: list[str] = []

        async for event in self._executor.execute_streaming(workflow, plan, messages):
            if isinstance(event, StreamTokenEvent):
                token = event.payload.get("content", "")
                final_content_parts.append(token)
                # Note: Restoration in streaming is tricky with placeholders.
                # In production, we yield tokens as-is and restore in the final turn storage.
                # However, for true safety, we'd need to restore/redact tokens too.
            yield event

        # 7. Persistence & Restoration
        if store and final_content_parts:
            content = "".join(final_content_parts)
            restored_content = self._restore_output(content, redaction_map)
            await store.append_turn(role="assistant", content=restored_content)
            await store.flush_to_long_term(content=restored_content, memory_type="episode")
            # Trigger context compression if history gets deep
            await self._trigger_compression(envelope.account_id, envelope.session_id, store)

        logger.info("orchestrator_stream_complete", workflow_id=str(workflow.id))

    async def _trigger_compression(self, account_id: str, session_id: str, store: ButlerSessionStore):
        """Monitor history depth and trigger anchored summarization if needed."""
        if not self._memory:
            return

        # Simple heuristic: Check turn count in context pack
        # We trigger compression when history length hits the limit (e.g. 20)
        context = await store.get_context(query="")
        if len(context.session_history) >= 20:
            logger.info("triggering_context_compression", session_id=session_id)
            await self._memory.compress_session(account_id, session_id)

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        return await self._db.get(Workflow, uuid.UUID(workflow_id))

    async def get_pending_approvals(self, account_id: str) -> list[ApprovalRequest]:
        result = await self._db.execute(select(ApprovalRequest).where(ApprovalRequest.account_id == uuid.UUID(account_id), ApprovalRequest.status == "pending"))
        return list(result.scalars().all())

    async def approve_request(self, approval_id: str, decision: str) -> Task:
        approval = await self._db.get(ApprovalRequest, uuid.UUID(approval_id))
        if not approval: raise OrchestratorErrors.APPROVAL_NOT_FOUND
        approval.status = decision
        approval.decided_at = datetime.now(UTC)
        task = await self._db.get(Task, approval.task_id)
        if decision == "approved":
            transition = TaskStateMachine.transition(task, "executing", "approval_granted")
            self._db.add(transition)
            await self._executor.resume_task(task)
        await self._db.commit()
        return task

    async def retry_task(self, task_id: str) -> Task:
        task = await self._db.get(Task, uuid.UUID(task_id))
        if not task: raise ValueError("Task not found")
        return task
