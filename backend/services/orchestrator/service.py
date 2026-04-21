from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.base_service import ButlerBaseService
from core.envelope import ButlerEnvelope
from core.observability import get_tracer
from domain.events.schemas import ButlerEvent, StreamFinalEvent
from domain.memory.contracts import IColdStore, IMemoryWriteStore, MemoryServiceContract
from domain.orchestrator.contracts import OrchestratorResult, OrchestratorServiceContract
from domain.orchestrator.exceptions import OrchestratorErrors
from domain.orchestrator.models import ApprovalRequest, Task, Workflow
from domain.orchestrator.runtime_kernel import (
    ExecutionContext,
    ExecutionMessage,
    RuntimeKernel,
)
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
    """Top-level Butler orchestration service.

    This service coordinates the lawful request flow:
    intake -> safety/redaction -> context/blending -> planning -> workflow/task
    creation -> kernel execution -> persistence -> memory update.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        redis: Redis,
        intake_proc: IntakeProcessor,
        planner: PlanEngine,
        executor: DurableExecutor,
        kernel: RuntimeKernel,
        blender: ButlerBlender,
        config: ButlerBaseConfig,
        memory_store: IMemoryWriteStore | None = None,
        cold_store: IColdStore | None = None,
        memory_service: MemoryServiceContract | None = None,
        tools_service: ToolsServiceContract | None = None,
        answering_engine: ISearchService | None = None,
        smart_router: object | None = None,
        feature_service: object | None = None,
        redaction_service: IRedactionService | None = None,
        content_guard: IContentGuard | None = None,
    ) -> None:
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
        self._features = feature_service
        self._redactor = redaction_service
        self._guard = content_guard
        self._tracer = get_tracer()

    async def on_startup(self) -> None:
        logger.info("orchestrator_service_startup_complete")

    async def on_shutdown(self) -> None:
        logger.info("orchestrator_service_shutdown_complete")

    def _make_session_store(
        self,
        session_id: str,
        account_id: str,
    ) -> ButlerSessionStore | None:
        if self._memory_store is None:
            return None

        return ButlerSessionStore(
            session_id=session_id,
            account_id=account_id,
            memory_store=self._memory_store,
            redis=self._redis,
            cold_store=self._cold_store,
        )

    async def _check_safety(self, text: str) -> dict[str, object]:
        if self._guard is None:
            return {"safe": True, "reason": "no_guard"}
        return await self._guard.check(text)

    def _redact_input(self, text: str) -> tuple[str, dict[str, str]]:
        if self._redactor is None:
            return text, {}
        redacted_text, redaction_map = self._redactor.redact(text)
        return redacted_text, redaction_map

    def _restore_output(self, text: str, redaction_map: dict[str, str]) -> str:
        if self._redactor is None:
            return text
        return self._redactor.restore(text, redaction_map)

    async def _generate_direct_llm_response(
        self,
        *,
        message: str,
        model: str | None,
    ) -> str:
        from domain.ml.contracts import ReasoningRequest
        from services.ml.registry import ModelProviderFactory, ModelSelector

        provider_type, model_name = ModelSelector.resolve(model)

        try:
            provider = ModelProviderFactory.get_provider(provider_type)
        except Exception as exc:
            logger.warning(
                "provider_init_failed",
                provider=provider_type,
                error=str(exc),
            )
            try:
                provider = ModelProviderFactory.get_provider("groq")
                model_name = "llama-3.3-70b-versatile"
            except Exception:
                return "I'm here to help. What would you like to do?"

        request = ReasoningRequest(
            prompt=f"User said: {message}",
            system_prompt=(
                "You are Butler, a helpful AI assistant. Respond naturally, clearly, and concisely."
            ),
            max_tokens=512,
            temperature=0.7,
            metadata={"model": model_name},
        )

        try:
            response = await provider.generate(request)
            logger.info(
                "llm_response_ok",
                provider=provider_type,
                model=model_name,
            )
            return response.content
        except Exception as exc:
            logger.warning(
                "llm_direct_response_failed",
                provider=provider_type,
                model=model_name,
                error=str(exc),
            )
            return "I'm here to help. What would you like to do?"

    async def _should_short_circuit_direct_response(
        self,
        *,
        intake_result: object,
        message: str,
    ) -> bool:
        if self._smart_router is None:
            return False

        from services.ml.smart_router import RouterRequest

        routing_request = RouterRequest(
            intent=intake_result,
            message=message,
            context_token_count=0,
        )
        routing_decision = self._smart_router.route(routing_request)
        return (
            routing_decision.tier.value < 2
            and getattr(intake_result, "intent", None) != "system_stats"
        )

    async def _build_blended_candidates(
        self,
        *,
        envelope: ButlerEnvelope,
        intake_result: object,
    ) -> Sequence[object]:
        signal = BlenderSignal(
            user_id=envelope.account_id,
            session_id=envelope.session_id,
            query=envelope.message,
            context={
                "intent": getattr(intake_result, "intent", ""),
                "mode": getattr(intake_result, "mode", ""),
                "channel": getattr(envelope, "channel", ""),
            },
        )
        return await self._blender.blend(signal)

    async def _build_messages(
        self,
        *,
        store: ButlerSessionStore | None,
        envelope: ButlerEnvelope,
        candidates: Sequence[object],
    ) -> list[ExecutionMessage]:
        messages: list[ExecutionMessage] = []

        if store is not None:
            context_pack = await store.get_context(query=envelope.message)

            if context_pack.summary_anchor:
                messages.append(
                    ExecutionMessage(
                        role="system",
                        content=(
                            f"PAST CONVERSATION SUMMARY (ANCHOR):\n{context_pack.summary_anchor}"
                        ),
                    )
                )

            for turn in context_pack.session_history:
                messages.append(
                    ExecutionMessage(
                        role=str(turn.get("role", "user")),
                        content=str(turn.get("content", "")),
                    )
                )

        if candidates:
            context_lines = [
                f"- [{candidate.source}] {candidate.content}" for candidate in candidates
            ]
            messages.append(
                ExecutionMessage(
                    role="system",
                    content="Context candidates:\n" + "\n".join(context_lines),
                )
            )

        messages.append(
            ExecutionMessage(
                role="user",
                content=envelope.message,
            )
        )
        return messages

    async def _create_workflow(
        self,
        *,
        envelope: ButlerEnvelope,
        intake_result: object,
        redaction_applied: bool,
        blender_count: int,
    ) -> Workflow:
        workflow = Workflow(
            id=uuid.uuid4(),
            account_id=uuid.UUID(envelope.account_id),
            session_id=envelope.session_id,
            intent=getattr(intake_result, "intent", ""),
            mode=getattr(intake_result, "mode", ""),
            context_snapshot={
                "channel": getattr(envelope, "channel", ""),
                "redacted": redaction_applied,
                "blender_count": blender_count,
            },
        )
        self._db.add(workflow)
        await self._db.flush()
        return workflow

    async def _create_plan(
        self,
        *,
        envelope: ButlerEnvelope,
        intake_result: object,
        candidates: Sequence[object],
    ) -> object:
        context_lines = [f"- [{candidate.source}] {candidate.content}" for candidate in candidates]
        augmented_prompt = (
            "Context:\n" + "\n".join(context_lines) + "\n\nUser request: " + envelope.message
        )

        return await self._planner.create_plan(
            intent=getattr(intake_result, "intent", ""),
            context={"prompt": augmented_prompt},
        )

    def _resolve_execution_model(self, envelope: ButlerEnvelope) -> str:
        return envelope.model or "auto"

    def _extract_toolset(self) -> list[object]:
        if self._tools is None:
            return []

        compiled_specs = getattr(self._tools, "_specs", {})
        if isinstance(compiled_specs, dict):
            return list(compiled_specs.values())
        return []

    async def _execute_via_kernel(
        self,
        *,
        envelope: ButlerEnvelope,
        workflow: Workflow,
        plan: object,
        messages: Sequence[ExecutionMessage],
    ) -> dict[str, object]:
        task = Task(
            id=uuid.uuid4(),
            workflow_id=workflow.id,
            account_id=uuid.UUID(envelope.account_id),
            session_id=envelope.session_id,
            task_type=getattr(workflow, "intent", "session"),
            state="queued",
            input_data={"message": envelope.message},
        )
        self._db.add(task)
        await self._db.flush()

        workflow.plan_schema = plan.to_dict() if hasattr(plan, "to_dict") else {}

        strategy = self._kernel.choose_strategy(task, workflow)
        execution_context = ExecutionContext(
            task=task,
            workflow=workflow,
            strategy=strategy,
            model=self._resolve_execution_model(envelope),
            toolset=self._extract_toolset(),
            system_prompt="You are Butler.",
            messages=list(messages),
            trace_id=str(uuid.uuid4()),
            account_id=envelope.account_id,
            session_id=envelope.session_id,
        )
        return await self._kernel.execute(execution_context)

    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        workflow: Workflow | None = None

        try:
            with self._tracer.span(
                "orchestrator.intake",
                attrs={"session_id": envelope.session_id, "mode": envelope.mode},
                account_id=envelope.account_id,
                session_id=envelope.session_id,
            ):
                safety = await self._check_safety(envelope.message)
                if not bool(safety.get("safe", False)):
                    return OrchestratorResult(
                        workflow_id=str(uuid.uuid4()),
                        content=(
                            "Request blocked by safety policy: "
                            f"{safety.get('reason', 'unknown_reason')}"
                        ),
                        actions=[],
                    )

                redacted_message, redaction_map = self._redact_input(envelope.message)
                redacted_envelope = envelope.model_copy(update={"message": redacted_message})

                store = self._make_session_store(
                    redacted_envelope.session_id,
                    redacted_envelope.account_id,
                )
                if store is not None:
                    await store.append_turn(role="user", content=redacted_envelope.message)

                intake_result = await self._intake.process(redacted_envelope)

                if await self._should_short_circuit_direct_response(
                    intake_result=intake_result,
                    message=redacted_envelope.message,
                ):
                    response_content = await self._generate_direct_llm_response(
                        message=redacted_envelope.message,
                        model=redacted_envelope.model,
                    )
                    return OrchestratorResult(
                        workflow_id=str(uuid.uuid4()),
                        content=response_content,
                        actions=[],
                    )

                candidates = await self._build_blended_candidates(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                )
                workflow = await self._create_workflow(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                    redaction_applied=bool(redaction_map),
                    blender_count=len(candidates),
                )
                plan = await self._create_plan(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                    candidates=candidates,
                )
                messages = await self._build_messages(
                    store=store,
                    envelope=redacted_envelope,
                    candidates=candidates,
                )

                execution_result = await self._execute_via_kernel(
                    envelope=redacted_envelope,
                    workflow=workflow,
                    plan=plan,
                    messages=messages,
                )

                response_content = str(execution_result.get("content", "") or "")
                if response_content:
                    output_safety = await self._check_safety(response_content)
                    if not bool(output_safety.get("safe", False)):
                        response_content = "[Blocked by output safety protocol]"
                    else:
                        response_content = self._restore_output(
                            response_content,
                            redaction_map,
                        )

                await self._db.commit()

                if store is not None and response_content:
                    await store.append_turn(role="assistant", content=response_content)
                    await store.flush_to_long_term(
                        content=response_content,
                        memory_type="episode",
                    )
                    await self._trigger_compression(
                        redacted_envelope.account_id,
                        redacted_envelope.session_id,
                        store,
                    )

                return OrchestratorResult(
                    workflow_id=str(workflow.id),
                    content=response_content,
                    actions=list(execution_result.get("actions", []) or []),
                )

        except Exception:
            if workflow is not None:
                workflow_id = str(workflow.id)
            else:
                workflow_id = str(uuid.uuid4())

            logger.exception(
                "orchestrator_intake_failed",
                workflow_id=workflow_id,
                session_id=envelope.session_id,
                account_id=envelope.account_id,
            )

            await self._db.rollback()

            return OrchestratorResult(
                workflow_id=workflow_id,
                content="Butler could not complete the request.",
                metadata={"phase": "intake_failed"},
            )

    async def intake_streaming(
        self,
        envelope: ButlerEnvelope,
    ) -> AsyncGenerator[ButlerEvent, None]:
        workflow: Workflow | None = None
        final_parts: list[str] = []

        try:
            with self._tracer.span(
                "orchestrator.intake_streaming",
                attrs={
                    "session_id": envelope.session_id,
                    "channel": getattr(envelope, "channel", ""),
                },
                account_id=envelope.account_id,
                session_id=envelope.session_id,
            ):
                safety = await self._check_safety(envelope.message)
                if not bool(safety.get("safe", False)):
                    yield StreamFinalEvent(
                        account_id=envelope.account_id,
                        session_id=envelope.session_id,
                        task_id="",
                        trace_id=str(uuid.uuid4()),
                        payload={
                            "content": (f"Safety Block: {safety.get('reason', 'unknown_reason')}")
                        },
                    )
                    return

                redacted_message, redaction_map = self._redact_input(envelope.message)
                redacted_envelope = envelope.model_copy(update={"message": redacted_message})

                store = self._make_session_store(
                    redacted_envelope.session_id,
                    redacted_envelope.account_id,
                )
                if store is not None:
                    await store.append_turn(role="user", content=redacted_envelope.message)

                intake_result = await self._intake.process(redacted_envelope)

                if await self._should_short_circuit_direct_response(
                    intake_result=intake_result,
                    message=redacted_envelope.message,
                ):
                    content = await self._generate_direct_llm_response(
                        message=redacted_envelope.message,
                        model=redacted_envelope.model,
                    )
                    yield StreamFinalEvent(
                        account_id=redacted_envelope.account_id,
                        session_id=redacted_envelope.session_id,
                        task_id="",
                        trace_id=str(uuid.uuid4()),
                        payload={"content": content},
                    )
                    return

                candidates = await self._build_blended_candidates(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                )
                workflow = await self._create_workflow(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                    redaction_applied=bool(redaction_map),
                    blender_count=len(candidates),
                )
                plan = await self._create_plan(
                    envelope=redacted_envelope,
                    intake_result=intake_result,
                    candidates=candidates,
                )
                messages = await self._build_messages(
                    store=store,
                    envelope=redacted_envelope,
                    candidates=candidates,
                )

                task = Task(
                    id=uuid.uuid4(),
                    workflow_id=workflow.id,
                    account_id=uuid.UUID(redacted_envelope.account_id),
                    session_id=redacted_envelope.session_id,
                    task_type=getattr(workflow, "intent", "session"),
                    state="queued",
                    input_data={"message": redacted_envelope.message},
                )
                self._db.add(task)
                await self._db.flush()

                workflow.plan_schema = plan.to_dict() if hasattr(plan, "to_dict") else {}
                strategy = self._kernel.choose_strategy(task, workflow)

                execution_context = ExecutionContext(
                    task=task,
                    workflow=workflow,
                    strategy=strategy,
                    model=self._resolve_execution_model(redacted_envelope),
                    toolset=self._extract_toolset(),
                    system_prompt="You are Butler.",
                    messages=list(messages),
                    trace_id=str(uuid.uuid4()),
                    account_id=redacted_envelope.account_id,
                    session_id=redacted_envelope.session_id,
                )

                async for event in self._kernel.execute_streaming(execution_context):
                    if isinstance(event, StreamFinalEvent):
                        content = str(event.payload.get("content", "") or "")
                        if content:
                            final_parts.append(content)
                    yield event

                await self._db.commit()

                restored_content = self._restore_output("".join(final_parts), redaction_map)
                if store is not None and restored_content:
                    await store.append_turn(role="assistant", content=restored_content)
                    await store.flush_to_long_term(
                        content=restored_content,
                        memory_type="episode",
                    )
                    await self._trigger_compression(
                        redacted_envelope.account_id,
                        redacted_envelope.session_id,
                        store,
                    )

                await self.record_interaction_outcome(
                    redacted_envelope.account_id,
                    "session",
                    True,
                )

                logger.info("orchestrator_stream_complete", workflow_id=str(workflow.id))

        except Exception:
            await self._db.rollback()
            logger.exception(
                "orchestrator_stream_failed",
                workflow_id=str(workflow.id) if workflow is not None else None,
                session_id=envelope.session_id,
                account_id=envelope.account_id,
            )
            yield StreamFinalEvent(
                account_id=envelope.account_id,
                session_id=envelope.session_id,
                task_id="",
                trace_id=str(uuid.uuid4()),
                payload={"content": "Butler could not complete the streamed request."},
            )

    async def record_interaction_outcome(
        self,
        user_id: str,
        tool_id: str,
        success: bool,
    ) -> None:
        if self._features is None:
            return
        await self._features.record_interaction_outcome(user_id, tool_id, success)
        logger.info(
            "interaction_outcome_recorded",
            user_id=user_id,
            tool_id=tool_id,
            success=success,
        )

    async def _trigger_compression(
        self,
        account_id: str,
        session_id: str,
        store: ButlerSessionStore,
    ) -> None:
        if self._memory is None:
            return

        context = await store.get_context(query="")
        if len(context.session_history) >= 20:
            logger.info(
                "triggering_context_compression",
                session_id=session_id,
                account_id=account_id,
            )
            await self._memory.compress_session(account_id, session_id)

    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        return await self._db.get(Workflow, uuid.UUID(workflow_id))

    async def get_pending_approvals(self, account_id: str) -> list[ApprovalRequest]:
        result = await self._db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.account_id == uuid.UUID(account_id),
                ApprovalRequest.status == "pending",
            )
        )
        return list(result.scalars().all())

    async def approve_request(self, approval_id: str, decision: str) -> Task:
        approval = await self._db.get(ApprovalRequest, uuid.UUID(approval_id))
        if approval is None:
            raise OrchestratorErrors.APPROVAL_NOT_FOUND

        approval.status = decision
        approval.decided_at = datetime.now(UTC)

        task = await self._db.get(Task, approval.task_id)
        if task is None:
            raise OrchestratorErrors.TASK_NOT_FOUND

        if decision == "approved":
            transition = TaskStateMachine.transition(
                task,
                "executing",
                "approval_granted",
            )
            self._db.add(transition)
            await self._executor.resume_task(task)

        await self._db.commit()
        return task

    async def retry_task(self, task_id: str) -> Task:
        task = await self._db.get(Task, uuid.UUID(task_id))
        if task is None:
            raise OrchestratorErrors.TASK_NOT_FOUND
        return task
