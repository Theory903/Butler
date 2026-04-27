"""Top-level Butler orchestration service.

Lawful flow:
  intake -> safety/redaction -> context/blending -> planning
  -> workflow creation -> durable execution -> persistence -> memory update
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.base_service import ButlerBaseService
from core.envelope import ButlerEnvelope, OrchestratorResult
from core.observability import get_tracer
from domain.events.schemas import ButlerEvent, StreamFinalEvent
from domain.memory.contracts import IColdStore, IMemoryWriteStore, MemoryServiceContract
from domain.orchestrator.contracts import (
    ExecutionMode,
    OrchestratorServiceContract,
)
from domain.orchestrator.exceptions import OrchestratorErrors
from domain.orchestrator.models import ApprovalRequest, Task, Workflow
from domain.orchestrator.runtime_kernel import (
    ExecutionContext,
    ExecutionMessage,
    ExecutionStrategy,
)
from domain.search.contracts import ISearchService
from domain.security.contracts import IContentGuard, IRedactionService
from domain.tools.contracts import ToolsServiceContract
from infrastructure.config import settings
from services.memory.session_store import ButlerSessionStore
from services.orchestrator.blender import BlenderSignal, ButlerBlender
from services.orchestrator.executor import ApprovalRequired, DurableExecutor
from services.orchestrator.intake import IntakeProcessor
from services.orchestrator.planner import Plan, PlanEngine
from services.orchestrator.graph import (
    compile_butler_graph,
    langgraph_available,
    run_fallback_graph,
)

logger = structlog.get_logger(__name__)


@dataclass
class PreparationState:
    """Carries the initialized state for both streaming and synchronous execution."""
    workflow: Workflow
    plan: Plan
    messages: list[ExecutionMessage]
    redacted_envelope: ButlerEnvelope
    redaction_map: dict[str, str]
    store: ButlerSessionStore | None


def _normalize_actions(raw_actions: Any) -> list[dict[str, Any]]:
    """Coerce backend action records to OrchestratorAction-compatible dicts."""
    if not raw_actions:
        return []
    try:
        items = list(raw_actions)
    except TypeError:
        return []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            normalized.append(
                {"type": "unknown", "payload": {"value": str(item)}, "status": "completed"}
            )
            continue
        
        action_type = (
            item.get("type")
            or item.get("tool_name")
            or item.get("name")
            or item.get("action")
            or "tool_call"
        )
        status = item.get("status")
        if not status:
            success = item.get("success")
            status = "completed" if success is True else "failed" if success is False else "completed"
            
        if "payload" in item and isinstance(item["payload"], dict):
            payload = dict(item["payload"])
        else:
            payload = {k: v for k, v in item.items() if k not in {"type", "status", "payload"}}
            
        normalized.append({"type": str(action_type), "payload": payload, "status": str(status)})
        
    return normalized


class OrchestratorService(ButlerBaseService, OrchestratorServiceContract):
    """Top-level Butler orchestration service."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        redis: Redis,
        intake_proc: IntakeProcessor,
        planner: PlanEngine,
        executor: DurableExecutor,
        blender: ButlerBlender,
        config: ButlerBaseConfig,
        memory_store: IMemoryWriteStore | None = None,
        cold_store: IColdStore | None = None,
        memory_service: MemoryServiceContract | None = None,
        tools_service: ToolsServiceContract | None = None,
        answering_engine: ISearchService | None = None,
        smart_router: Any | None = None,
        feature_service: Any | None = None,
        redaction_service: IRedactionService | None = None,
        content_guard: IContentGuard | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        super().__init__(config=config)
        self._db = db
        self._redis = redis
        self._intake = intake_proc
        self._planner = planner
        self._executor = executor
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
        self._checkpointer = checkpointer
        self._compiled_graph: Any | None = None

    async def on_startup(self) -> None:
        logger.info("orchestrator_service_startup_complete")

    async def on_shutdown(self) -> None:
        logger.info("orchestrator_service_shutdown_complete")

    # -------------------------------------------------------------------------
    # Graph Context Provider
    # -------------------------------------------------------------------------

    def _build_graph_context(self) -> dict:
        """Build context for LangGraph execution."""
        return {
            "db": self._db,
            "redis": self._redis,
            "memory_store": self._memory_store,
            "cold_store": self._cold_store,
            "memory_service": self._memory,
            "tools_service": self._tools,
            "answering_engine": self._answering_engine,
            "smart_router": self._smart_router,
            "feature_service": self._features,
            "redaction_service": self._redactor,
            "content_guard": self._guard,
            "checkpointer": self._checkpointer,
            "intake_proc": self._intake,
            "planner": self._planner,
            "executor": self._executor,
            "blender": self._blender,
        }

    # -------------------------------------------------------------------------
    # Safety Check
    # -------------------------------------------------------------------------

    async def _check_safety(self, content: str) -> dict:
        """Check content safety using the content guard."""
        if self._guard is None:
            return {"safe": True, "reason": "no_guard_configured"}
        try:
            result = await self._guard.check(content)
            return result if isinstance(result, dict) else {"safe": bool(result)}
        except Exception as exc:
            logger.warning("safety_check_failed", error=str(exc))
            return {"safe": True, "reason": "check_failed"}

    # -------------------------------------------------------------------------
    # Redaction & Storage Helpers
    # -------------------------------------------------------------------------

    def _redact_input(self, message: str) -> tuple[str, dict]:
        """Redact sensitive content from input message."""
        if self._redactor is None:
            return message, {}
        try:
            return self._redactor.redact(message)
        except Exception as exc:
            logger.warning("redaction_failed", error=str(exc))
            return message, {}

    def _restore_output(self, content: str, redaction_map: dict) -> str:
        """Restore redacted content from output."""
        if not redaction_map:
            return content
        for original, redacted in redaction_map.items():
            content = content.replace(redacted, original)
        return content

    def _make_session_store(self, session_id: str, account_id: str) -> ButlerSessionStore | None:
        """Create a session store for the given session."""
        if self._memory_store is None:
            return None
        try:
            return ButlerSessionStore(
                session_id=session_id,
                account_id=account_id,
                memory_store=self._memory_store,
                redis=self._redis,
            )
        except Exception as exc:
            logger.warning("session_store_creation_failed", error=str(exc))
            return None

    # -------------------------------------------------------------------------
    # Short-circuit & Direct Response Helpers
    # -------------------------------------------------------------------------

    async def _should_short_circuit_direct_response(self, intake_result: Any, message: str) -> bool:
        """Determine if request should be short-circuited with direct response."""
        return False

    async def _generate_direct_llm_response(self, message: str, model: str | None = None) -> str:
        """Generate a direct LLM response without full orchestration."""
        return "Direct response not implemented"

    # -------------------------------------------------------------------------
    # Context & Planning Helpers
    # -------------------------------------------------------------------------

    async def _build_blended_candidates(self, envelope: ButlerEnvelope, intake_result: Any) -> list:
        """Build blended context candidates from memory and search."""
        return []

    async def _create_workflow(self, envelope: ButlerEnvelope, intake_result: Any, redaction_applied: bool, blender_count: int) -> Workflow:
        """Create a workflow for execution."""
        workflow = Workflow(
            tenant_id=envelope.account_id,
            account_id=envelope.account_id,
            session_id=envelope.session_id,
            mode=envelope.mode or "agentic",
            status="pending",
            state_snapshot={"message": envelope.message},
        )
        self._db.add(workflow)
        await self._db.flush()
        return workflow

    async def _create_plan(self, envelope: ButlerEnvelope, intake_result: Any, candidates: list) -> Plan:
        """Create an execution plan."""
        from services.orchestrator.planner import Step
        
        return Plan(
            intent="general",
            execution_mode=ExecutionMode.WORKFLOW,
            steps=[
                Step(
                    action="respond",
                    params={"message": envelope.message},
                ),
            ],
        )

    async def _build_messages(self, store: ButlerSessionStore | None, envelope: ButlerEnvelope, candidates: list) -> list[ExecutionMessage]:
        """Build execution messages from context."""
        return [ExecutionMessage(role="user", content=envelope.message)]

    # -------------------------------------------------------------------------
    # Compression Helper
    # -------------------------------------------------------------------------

    async def _trigger_compression(self, account_id: str, session_id: str, store: ButlerSessionStore) -> None:
        """Trigger memory compression if needed."""
        pass

    # -------------------------------------------------------------------------
    # Core Orchestration Pipeline
    # -------------------------------------------------------------------------

    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        """Primary entry point for synchronous execution."""
        logger.info("orchestrator_intake_entry", session_id=envelope.session_id)
        
        try:
            if langgraph_available():
                if self._compiled_graph is None:
                    self._compiled_graph = compile_butler_graph(
                        core_runner=self._intake_core,
                        context_provider=self._build_graph_context,
                        checkpointer=self._checkpointer,
                    )

                state = await self._compiled_graph.ainvoke(
                    {"envelope": envelope, "graph_path": []},
                    config={
                        "configurable": {
                            "thread_id": envelope.session_id,
                            "checkpoint_ns": envelope.identity.tenant_id if envelope.identity else envelope.account_id,
                        }
                    },
                )
                
                final_result = state.get("final_result")
                if isinstance(final_result, OrchestratorResult):
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata.update({"graph_runtime": True, "fallback_used": False})
                    return final_result
            else:
                state = await run_fallback_graph(
                    envelope=envelope,
                    core_runner=self._intake_core,
                    context_provider=self._build_graph_context,
                )
                final_result = state.get("final_result")
                if isinstance(final_result, OrchestratorResult):
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata.update({"graph_runtime": False, "fallback_used": True})
                    return final_result
                    
        except Exception as exc:
            logger.warning(
                "orchestrator_graph_execution_failed",
                session_id=envelope.session_id,
                error=str(exc),
                exc_info=True,
            )

        # Ultimate fallback
        logger.info("orchestrator_falling_back_to_intake_core", session_id=envelope.session_id)
        result = await self._intake_core(envelope)
        result.metadata = result.metadata or {}
        result.metadata.update({"graph_runtime": False, "fallback_used": True})
        return result

    async def _intake_core(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        workflow_id: str | None = None

        try:
            with self._tracer.span(
                "orchestrator.intake",
                attrs={"session_id": envelope.session_id, "mode": envelope.mode},
                account_id=envelope.account_id,
                session_id=envelope.session_id,
            ):
                # 1. Pipeline Setup & Guardrails
                state_or_result = await self._prepare_execution_state(envelope)
                
                # If preparation returned a direct response (e.g. Safety block or short-circuit)
                if isinstance(state_or_result, OrchestratorResult):
                    return state_or_result
                    
                state: PreparationState = state_or_result
                workflow_id = str(state.workflow.id)

                # 2. Execution Routing
                if state.plan.execution_mode in {ExecutionMode.AGENTIC, ExecutionMode.DETERMINISTIC}:
                    execution_result = await self._execute_agentic(state)
                    
                    if isinstance(execution_result, OrchestratorResult):
                        return execution_result  # Awaiting approval short-circuit
                else:
                    await self._db.flush()
                    await self._db.commit()
                    execution_result = await self._executor.execute_workflow(
                        workflow=state.workflow,
                        plan=state.plan,
                    )

                # 3. Finalize & Persist
                response_content = str(getattr(execution_result, "content", "") or "")
                response_content = await self._finalize_output(response_content, state)

                # Map Token Usage safely
                input_tokens = getattr(execution_result, "token_usage", getattr(execution_result, "input_tokens", 0))
                output_tokens = getattr(execution_result, "token_usage", getattr(execution_result, "output_tokens", 0))
                if hasattr(input_tokens, "input_tokens"):
                    input_tokens, output_tokens = input_tokens.input_tokens, input_tokens.output_tokens

                return OrchestratorResult(
                    workflow_id=workflow_id,
                    content=response_content or "",
                    actions=_normalize_actions(execution_result.actions),
                    session_id=envelope.session_id,
                    request_id=envelope.request_id,
                    metadata={
                        **getattr(execution_result, "metadata", {}),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "duration_ms": getattr(execution_result, "duration_ms", 0),
                    },
                )

        except Exception as exc:
            workflow_id = workflow_id or str(uuid.uuid4())
            logger.exception(
                "orchestrator_intake_failed",
                workflow_id=workflow_id,
                session_id=envelope.session_id,
                account_id=envelope.account_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            await self._db.rollback()
            return OrchestratorResult(
                workflow_id=workflow_id,
                session_id=envelope.session_id,
                request_id=envelope.request_id,
                content="Butler could not complete the request.",
                actions=[],
                metadata={"phase": "intake_failed"},
            )

    async def intake_streaming(self, envelope: ButlerEnvelope) -> AsyncGenerator[ButlerEvent]:
        workflow_id: str | None = None
        final_parts: list[str] = []

        try:
            with self._tracer.span(
                "orchestrator.intake_streaming",
                attrs={"session_id": envelope.session_id, "channel": getattr(envelope, "channel", "")},
                account_id=envelope.account_id,
                session_id=envelope.session_id,
            ):
                state_or_result = await self._prepare_execution_state(envelope)

                if isinstance(state_or_result, OrchestratorResult):
                    yield StreamFinalEvent(
                        account_id=envelope.account_id,
                        session_id=envelope.session_id,
                        task_id="",
                        trace_id=str(uuid.uuid4()),
                        payload={"content": state_or_result.content},
                    )
                    return

                state: PreparationState = state_or_result
                workflow_id = str(state.workflow.id)

                if state.plan.execution_mode in {ExecutionMode.AGENTIC, ExecutionMode.DETERMINISTIC}:
                    strategy = ExecutionStrategy.HERMES_AGENT if state.plan.execution_mode == ExecutionMode.AGENTIC else ExecutionStrategy.DETERMINISTIC
                    
                    task = Task(
                        id=uuid.uuid4(),
                        workflow_id=state.workflow.id,
                        task_type="orchestrator",
                        status="pending",
                        input_data={"prompt": state.redacted_envelope.message},
                    )
                    self._db.add(task)
                    await self._db.flush()
                    await self._db.commit()

                    context = ExecutionContext(
                        task=task,
                        workflow=state.workflow,
                        strategy=strategy,
                        model=state.redacted_envelope.model or self._executor._model,
                        toolset=self._executor._extract_toolset(),
                        system_prompt=self._executor._system_prompt,
                        messages=state.messages,
                        trace_id=self._tracer.get_current_trace_id() or f"trc_{uuid.uuid4().hex[:12]}",
                        account_id=state.redacted_envelope.account_id,
                        session_id=state.redacted_envelope.session_id,
                    )
                    event_gen = self._executor._kernel.execute_streaming(context)
                else:
                    task = await self._create_streaming_task(workflow=state.workflow, envelope=state.redacted_envelope)
                    await self._db.flush()
                    await self._db.commit()
                    event_gen = self._executor.execute_streaming(
                        workflow=state.workflow,
                        task=task,
                        messages=state.messages,
                    )

                async for event in event_gen:
                    if isinstance(event, StreamFinalEvent):
                        content = str(event.payload.get("content", "") or "")
                        if content:
                            final_parts.append(content)
                    yield event

                await self._finalize_output("".join(final_parts), state)
                await self.record_interaction_outcome(state.redacted_envelope.account_id, "session", True)

                logger.info("orchestrator_stream_complete", workflow_id=workflow_id)

        except Exception:
            await self._db.rollback()
            logger.exception("orchestrator_stream_failed", workflow_id=workflow_id, session_id=envelope.session_id)
            yield StreamFinalEvent(
                account_id=envelope.account_id,
                session_id=envelope.session_id,
                task_id="",
                trace_id=str(uuid.uuid4()),
                payload={"content": "Butler could not complete the streamed request."},
            )

    # -------------------------------------------------------------------------
    # Pipeline Helpers
    # -------------------------------------------------------------------------

    async def _prepare_execution_state(self, envelope: ButlerEnvelope) -> PreparationState | OrchestratorResult:
        """Consolidates Guardrails, Redaction, Storage, and Context Preparation."""
        
        # 1. Safety
        safety = await self._check_safety(envelope.message)
        if not bool(safety.get("safe", False)):
            return OrchestratorResult(
                workflow_id=str(uuid.uuid4()),
                session_id=envelope.session_id,
                request_id=envelope.request_id,
                content=f"Request blocked by safety policy: {safety.get('reason', 'unknown_reason')}",
                actions=[],
            )

        # 2. Redaction & Storage
        redacted_message, redaction_map = self._redact_input(envelope.message)
        redacted_envelope = envelope.model_copy(update={"message": redacted_message})

        store = self._make_session_store(redacted_envelope.session_id, redacted_envelope.account_id)
        if store is not None:
            await store.append_turn(role="user", content=redacted_envelope.message)

        # 3. Intake & Short Circuit
        intake_result = await self._intake.process(redacted_envelope)

        if await self._should_short_circuit_direct_response(intake_result=intake_result, message=redacted_envelope.message):
            content = await self._generate_direct_llm_response(message=redacted_envelope.message, model=redacted_envelope.model)
            return OrchestratorResult(
                workflow_id=str(uuid.uuid4()),
                session_id=envelope.session_id,
                request_id=envelope.request_id,
                content=content,
                actions=[],
            )

        # 4. Context & Planning
        candidates = await self._build_blended_candidates(envelope=redacted_envelope, intake_result=intake_result)
        workflow = await self._create_workflow(
            envelope=redacted_envelope,
            intake_result=intake_result,
            redaction_applied=bool(redaction_map),
            blender_count=len(candidates),
        )
        plan = await self._create_plan(envelope=redacted_envelope, intake_result=intake_result, candidates=candidates)
        messages = await self._build_messages(store=store, envelope=redacted_envelope, candidates=candidates)

        if plan.execution_mode in {ExecutionMode.AGENTIC, ExecutionMode.DETERMINISTIC}:
            workflow.plan_schema = plan.to_dict()

        return PreparationState(
            workflow=workflow,
            plan=plan,
            messages=messages,
            redacted_envelope=redacted_envelope,
            redaction_map=redaction_map,
            store=store,
        )

    async def _execute_agentic(self, state: PreparationState) -> Any | OrchestratorResult:
        """Handles agentic/deterministic routing and handles approvals cleanly."""
        strategy = ExecutionStrategy.HERMES_AGENT if state.plan.execution_mode == ExecutionMode.AGENTIC else ExecutionStrategy.DETERMINISTIC
        
        task = Task(
            id=uuid.uuid4(),
            workflow_id=state.workflow.id,
            task_type="orchestrator",
            input_data={"prompt": state.redacted_envelope.message},
        )
        self._db.add(task)
        await self._db.flush()

        context = ExecutionContext(
            task=task,
            workflow=state.workflow,
            strategy=strategy,
            model=state.redacted_envelope.model or self._executor._model,
            toolset=self._executor._extract_toolset(),
            system_prompt=self._executor._system_prompt,
            messages=state.messages,
            trace_id=self._tracer.get_current_trace_id() or f"trc_{uuid.uuid4().hex[:12]}",
            account_id=state.redacted_envelope.account_id,
            tenant_id=state.redacted_envelope.account_id,
            session_id=state.redacted_envelope.session_id,
        )

        try:
            res = await self._executor._kernel.execute_result(context)
        except ApprovalRequired as approval:
            approval_request = await self._executor.suspend_for_approval(task=task, workflow=state.workflow, error=approval)
            return OrchestratorResult(
                workflow_id=str(state.workflow.id),
                content=approval.description,
                actions=[],
                requires_approval=True,
                approval_id=str(approval_request.id),
                session_id=state.redacted_envelope.session_id,
                request_id=state.redacted_envelope.request_id,
                metadata={
                    "status": "awaiting_approval",
                    "tool_name": approval.tool_name,
                    "risk_tier": approval.risk_tier,
                },
            )

        task.completed_at = datetime.now(UTC)
        task.status = "completed"
        task.output_data = res.to_legacy_dict()
        await self._db.commit()
        return res

    async def _finalize_output(self, content: str, state: PreparationState) -> str:
        """Restores redacted content, executes output guardrails, and persists memory."""
        if not content:
            return ""

        output_safety = await self._check_safety(content)
        if not bool(output_safety.get("safe", False)):
            content = "[Blocked by output safety protocol]"
        else:
            content = self._restore_output(content, state.redaction_map)

        if state.store is not None:
            await state.store.append_turn(role="assistant", content=content)
            await state.store.flush_to_long_term(content=content, memory_type="episode")
            await self._trigger_compression(state.redacted_envelope.account_id, state.redacted_envelope.session_id, state.store)
            
        return content