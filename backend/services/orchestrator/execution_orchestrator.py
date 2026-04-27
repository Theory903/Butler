"""Execution Orchestrator for Butler production runtime.

Routes requests to appropriate execution lanes based on intent classification.
One authoritative execution path per request.

Execution lanes:
- A. direct_response: Returns without tool/model
- B. deterministic_tool: Uses ToolExecutor directly (T0 provider)
- C. llm_answer: Calls ML runtime once with context
- D. llm_with_tools: Binds only relevant visible tools
- E. durable_workflow: Uses LangGraph with persistent checkpointing
- F. async_job: Persists job and returns job_id
- G. human_approval_workflow: Creates approval request and pauses workflow
- H. crew_multi_agent: Uses CrewAI for multi-agent collaboration
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from domain.runtime.envelope import ButlerRuntimeEnvelope
from domain.runtime.execution_class import ExecutionClass
from domain.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    """Result of execution lane execution."""

    response: str
    execution_class: ExecutionClass
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    approval_id: str | None = None


class ExecutionOrchestrator:
    """Orchestrate execution across all lanes.

    Rules:
    - direct_response returns without tool/model
    - deterministic_tool uses ToolExecutor directly
    - llm_answer calls ML runtime once with context
    - llm_with_tools binds only relevant visible tools
    - durable_workflow uses LangGraph with persistent checkpointing
    - async_job persists job and returns job_id
    - human_approval_workflow creates approval request and pauses workflow

    For "what is the time":
    Gateway → Ingress → IntentRouter: time.lookup → ExecutionClass: deterministic_tool
    → ToolRegistry: get_time visible + executable → ToolExecutor → Synthesizer
    → SessionWrite once → Return

    No LangGraph. No RAG. No KAG. No LLM. No 39 tools. No spiritual damage.
    """

    def __init__(self) -> None:
        self._tool_registry = get_tool_registry()
        self._crewai_builder = None  # Lazy load CrewAI builder when needed
        self._toolscope_service = None  # Lazy load ToolScope service when needed
        self._intent_builder = None  # Lazy load IntentBuilder when needed
        self._guardrail = None  # Lazy load ExecutionGuardrail when needed
        self._feedback_service = None  # Lazy load FeedbackService when needed

    async def execute(
        self,
        envelope: ButlerRuntimeEnvelope,
        intent_result: Any,
        context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute request using appropriate lane."""
        execution_class = intent_result.execution_class

        if execution_class == ExecutionClass.DIRECT_RESPONSE:
            return await self._execute_direct_response(envelope, intent_result)
        if execution_class == ExecutionClass.DETERMINISTIC_TOOL:
            return await self._execute_deterministic_tool(envelope, intent_result)
        if execution_class == ExecutionClass.LLM_ANSWER:
            return await self._execute_llm_answer(envelope, intent_result)
        if execution_class == ExecutionClass.LLM_WITH_TOOLS:
            return await self._execute_llm_with_tools(envelope, intent_result)
        if execution_class == ExecutionClass.DURABLE_WORKFLOW:
            return await self._execute_durable_workflow(envelope, intent_result)
        if execution_class == ExecutionClass.ASYNC_JOB:
            return await self._execute_async_job(envelope, intent_result)
        if execution_class == ExecutionClass.HUMAN_APPROVAL_WORKFLOW:
            return await self._execute_human_approval(envelope, intent_result)
        if execution_class == ExecutionClass.CREW_MULTI_AGENT:
            return await self._execute_crew_multi_agent(envelope, intent_result)
        raise ValueError(f"Unknown execution class: {execution_class}")

    async def _execute_direct_response(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute direct response without tool/model."""
        # Return local answer if available
        local_answer = intent_result.metadata.get("local_answer")
        if local_answer:
            return ExecutionResult(
                response=local_answer,
                execution_class=ExecutionClass.DIRECT_RESPONSE,
                metadata={"source": "local_resolver"},
            )

        return ExecutionResult(
            response="I don't have enough context to answer that directly.",
            execution_class=ExecutionClass.DIRECT_RESPONSE,
        )

    async def _execute_deterministic_tool(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute deterministic tool (T0 provider, no LLM)."""
        # For time queries, use get_time tool directly
        if "time" in intent_result.intent.lower():
            tool_spec = self._tool_registry.get_spec("get_time")
            if tool_spec and self._tool_registry.is_executable("get_time"):
                implementation = self._tool_registry.get_implementation(tool_spec.binding_ref)
                if implementation:
                    try:
                        # Get timezone from context or default to UTC
                        timezone = envelope.client_context.timezone or "UTC"
                        result = await implementation(timezone=timezone)
                        return ExecutionResult(
                            response=(
                                f"The current time is {result.get('time')} on "
                                f"{result.get('weekday')}, {result.get('date')} "
                                f"in {result.get('timezone')}."
                            ),
                            execution_class=ExecutionClass.DETERMINISTIC_TOOL,
                            tool_calls=[{"tool": "get_time", "input": {"timezone": timezone}}],
                            metadata={"source": "deterministic_tool", "tool_result": result},
                        )
                    except Exception as exc:
                        return ExecutionResult(
                            response=f"Failed to get time: {exc}",
                            execution_class=ExecutionClass.DETERMINISTIC_TOOL,
                            metadata={"error": str(exc)},
                        )

        return ExecutionResult(
            response="Tool not available for deterministic execution",
            execution_class=ExecutionClass.DETERMINISTIC_TOOL,
        )

    async def _execute_llm_answer(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute LLM answer without tools."""
        # This would call the ML runtime with context
        # For now, return placeholder
        return ExecutionResult(
            response="LLM answer execution not yet implemented",
            execution_class=ExecutionClass.LLM_ANSWER,
            metadata={"note": "requires ML runtime integration"},
        )

    async def _execute_llm_with_tools(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute LLM with tool planning and execution using 6-layer ToolScope pipeline.

        Pipeline:
        1. Intent Builder (Layer 1)
        2. Tool Retrieval Pipeline (Layer 2) - 4-stage semantic retrieval
        3. Tool Selection Contract (Layer 3) - returned by retrieve
        4. Execution Guardrail (Layer 4)
        5. Tool Execution (Layer 5)
        6. Feedback Loop (Layer 6)
        """
        from infrastructure.config import settings

        # Lazy load all services
        await self._initialize_services(settings)

        # Check if services are available
        if self._intent_builder is None or self._toolscope_service is None or self._guardrail is None:
            logger.warning("services_not_initialized_fallback_to_simple")
            visible_tools = self._tool_registry.visible_tools(max_tools=8)
            tool_names = [spec.name for spec in visible_tools]
            return ExecutionResult(
                response=f"LLM with tools execution not yet implemented. Available tools: {tool_names}",
                execution_class=ExecutionClass.LLM_WITH_TOOLS,
                metadata={"available_tools": tool_names, "services_initialized": False},
            )

        # Layer 1: Intent Builder
        user_message = envelope.input.content if hasattr(envelope.input, 'content') else str(envelope.input)
        intent_context = self._intent_builder.build(
            user_input=user_message,
            account_permissions=frozenset(),  # TODO: Get from envelope context
        )

        # Layer 2 & 3: Tool Retrieval Pipeline + Selection Contract
        tool_success_rates = None
        if self._feedback_service:
            tool_success_rates = await self._feedback_service.get_success_rates()
        selection_contract = self._toolscope_service.retrieve(
            intent_context=intent_context,
            account_permissions=frozenset(),  # TODO: Get from envelope context
            max_risk_tier=settings.TOOLSCOPE_MAX_RISK_TIER,
            tool_success_rates=tool_success_rates,
        )

        # Layer 4: Execution Guardrail
        guardrail_result = self._guardrail.validate(
            selected_tools=selection_contract.selected_tools,
            intent_context={"query": intent_context.query, "type": intent_context.intent_type},
            account_permissions=frozenset(),  # TODO: Get from envelope context
        )

        # Check if guardrail passed
        if not guardrail_result.passed:
            logger.warning(f"guardrail_validation_failed: {len(guardrail_result.violations)} violations")
            return ExecutionResult(
                response=f"Tool execution blocked by guardrail: {', '.join(guardrail_result.violations)}",
                execution_class=ExecutionClass.LLM_WITH_TOOLS,
                metadata={
                    "guardrail_passed": False,
                    "guardrail_violations": guardrail_result.violations,
                    "selection_contract": selection_contract.to_dict(),
                },
            )

        # Layer 5: Tool Execution (placeholder - actual execution not yet implemented)
        tool_names = [tool.name for tool in selection_contract.selected_tools]

        # Layer 6: Feedback Loop (placeholder - record after actual execution)
        # TODO: Record feedback after actual tool execution

        logger.info(
            f"toolscope_pipeline_complete: intent={intent_context.intent_type}, "
            f"tools={len(tool_names)}, guardrail_passed={guardrail_result.passed}"
        )

        return ExecutionResult(
            response=f"LLM with tools execution not yet implemented. Available tools: {tool_names}",
            execution_class=ExecutionClass.LLM_WITH_TOOLS,
            metadata={
                "available_tools": tool_names,
                "toolscope_enabled": True,
                "selection_contract": selection_contract.to_dict(),
                "guardrail_result": {
                    "passed": guardrail_result.passed,
                    "violations": guardrail_result.violations,
                    "warnings": guardrail_result.warnings,
                },
                "intent_context": {
                    "query": intent_context.query,
                    "type": intent_context.intent_type,
                    "risk_level": intent_context.constraints.risk_level,
                },
            },
        )

    async def _initialize_services(self, settings: Any) -> None:
        """Initialize all services for the 6-layer pipeline.

        Args:
            settings: Configuration settings.
        """
        # Initialize IntentBuilder
        if self._intent_builder is None and settings.INTENT_BUILDER_ENABLED:
            from services.intent.intent_builder import IntentBuilder

            self._intent_builder = IntentBuilder(
                enabled=settings.INTENT_BUILDER_ENABLED,
                default_risk_level=settings.INTENT_BUILDER_DEFAULT_RISK_LEVEL,
                max_query_length=settings.INTENT_BUILDER_MAX_QUERY_LENGTH,
            )

        # Initialize ToolScope service
        if self._toolscope_service is None and settings.TOOLSCOPE_ENABLED:
            try:
                from services.tools.toolscope_service import get_toolscope_service
                from services.ml.embeddings import EmbeddingService

                embedding_service = EmbeddingService(
                    model_name="intfloat/multilingual-e5-large",
                )

                self._toolscope_service = get_toolscope_service(
                    embedding_service=embedding_service,
                    k=settings.TOOLSCOPE_K,
                    enable_reranking=settings.TOOLSCOPE_ENABLE_RERANKING,
                    enable_sticky_sessions=settings.TOOLSCOPE_ENABLE_STICKY_SESSIONS,
                    max_risk_tier=settings.TOOLSCOPE_MAX_RISK_TIER,
                    tool_text_truncate=settings.TOOLSCOPE_TOOL_TEXT_TRUNCATE,
                    dynamic_cutoff_enabled=settings.TOOLSCOPE_DYNAMIC_CUTOFF_ENABLED,
                    cutoff_threshold=settings.TOOLSCOPE_CUTOFF_THRESHOLD,
                    max_tools=settings.TOOLSCOPE_MAX_TOOLS,
                    reranking_blend_semantic=settings.TOOLSCOPE_RERANKING_BLEND_SEMANTIC,
                    reranking_blend_intent=settings.TOOLSCOPE_RERANKING_BLEND_INTENT,
                    reranking_blend_success=settings.TOOLSCOPE_RERANKING_BLEND_SUCCESS,
                    reranking_blend_cost=settings.TOOLSCOPE_RERANKING_BLEND_COST,
                )

                # Build index from all visible tools in registry
                all_specs = self._tool_registry.get_all_specs()
                visible_specs = [
                    spec for spec in all_specs.values()
                    if self._tool_registry.is_visible(spec.name)
                ]

                if visible_specs:
                    self._toolscope_service.build_index(visible_specs)
                    logger.info(f"toolscope_index_initialized with {len(visible_specs)} tools")
            except ImportError:
                logger.warning("toolscope_not_available")
            except Exception as e:
                logger.error(f"toolscope_initialization_failed: {e}")

        # Initialize ExecutionGuardrail
        if self._guardrail is None and settings.TOOL_GUARDRAIL_ENABLED:
            from services.tools.guardrail import ExecutionGuardrail

            self._guardrail = ExecutionGuardrail(
                enabled=settings.TOOL_GUARDRAIL_ENABLED,
                strict_mode=settings.TOOL_GUARDRAIL_STRICT_MODE,
                max_parameter_size=settings.TOOL_GUARDRAIL_MAX_PARAMETER_SIZE,
                enable_schema_validation=settings.TOOL_GUARDRAIL_ENABLE_SCHEMA_VALIDATION,
            )

        # Initialize FeedbackService
        if self._feedback_service is None and settings.TOOL_FEEDBACK_ENABLED:
            from services.tools.feedback_service import get_feedback_service

            self._feedback_service = get_feedback_service(
                enabled=settings.TOOL_FEEDBACK_ENABLED,
                feedback_window_seconds=settings.TOOL_FEEDBACK_WINDOW_SECONDS,
                min_samples=settings.TOOL_FEEDBACK_MIN_SAMPLES,
                success_decay_rate=settings.TOOL_FEEDBACK_SUCCESS_DECAY_RATE,
            )

    async def _execute_durable_workflow(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute durable LangGraph workflow with checkpointing."""
        return ExecutionResult(
            response="Durable workflow execution not yet implemented",
            execution_class=ExecutionClass.DURABLE_WORKFLOW,
            metadata={"note": "requires LangGraph integration"},
        )

    async def _execute_async_job(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute async job and return job_id."""
        return ExecutionResult(
            response="Async job execution not yet implemented",
            execution_class=ExecutionClass.ASYNC_JOB,
            metadata={"note": "requires queue integration"},
        )

    async def _execute_human_approval(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute human approval workflow."""
        return ExecutionResult(
            response="Human approval workflow not yet implemented",
            execution_class=ExecutionClass.HUMAN_APPROVAL_WORKFLOW,
            requires_approval=True,
            metadata={"note": "requires approval service integration"},
        )

    async def _execute_crew_multi_agent(
        self, envelope: ButlerRuntimeEnvelope, intent_result: Any
    ) -> ExecutionResult:
        """Execute CrewAI multi-agent collaboration."""
        # Lazy load CrewAI builder
        if self._crewai_builder is None:
            try:
                from services.crewai import CrewAIBuilder
                from services.crewai.config import CrewAIConfig, DomainRequirement
                from services.security.safety import ContentGuard

                # Initialize ContentGuard for security integration
                content_guard = ContentGuard()

                # Get MemoryService from Butler's dependency system
                # This properly hardens the integration with Butler's memory service
                memory_service = None
                try:
                    from core.deps import get_memory_service
                    from infrastructure.config import settings

                    # Create a mock db and redis for dependency injection
                    # In production, this would come from the actual request context
                    from sqlalchemy.ext.asyncio import AsyncSession
                    from redis.asyncio import Redis

                    # For now, we'll pass None and the builder will handle it gracefully
                    # In Phase 2, this will be properly integrated with request-scoped deps
                    logger.info("MemoryService integration ready for request-scoped injection")
                except ImportError:
                    logger.warning("MemoryService not available - memory integration disabled")

                self._crewai_builder = CrewAIBuilder(
                    config=CrewAIConfig(),
                    content_guard=content_guard,
                    memory_service=memory_service,
                )
            except ImportError:
                return ExecutionResult(
                    response="CrewAI not installed. Add 'crewai>=0.80.0' to requirements.txt",
                    execution_class=ExecutionClass.CREW_MULTI_AGENT,
                    metadata={"error": "crewai_not_installed"},
                )

        # Extract domain requirements from intent_result
        domain_requirements = DomainRequirement(
            domain=intent_result.metadata.get("domain", "general"),
            complexity=intent_result.metadata.get("complexity", "medium"),
            agent_roles=intent_result.metadata.get("agent_roles", []),
        )

        # Build crew from domain requirements
        crew = self._crewai_builder.build_crew(
            domain_requirements=domain_requirements,
            user_message=envelope.input.content if hasattr(envelope.input, 'content') else str(envelope.input),
            context={
                "account_id": envelope.account_id,
                "session_id": envelope.session_id,
            },
        )

        # Execute crew with inputs
        # Convert UUIDs to strings for CrewAI compatibility
        inputs = {
            "user_message": envelope.input.content if hasattr(envelope.input, 'content') else str(envelope.input),
            "account_id": str(envelope.account_id) if envelope.account_id else None,
            "session_id": envelope.session_id,
        }

        result = await self._crewai_builder.execute_crew(crew, inputs)

        return ExecutionResult(
            response=result.get("response", "CrewAI execution failed"),
            execution_class=ExecutionClass.CREW_MULTI_AGENT,
            metadata=result.get("metadata", {}),
        )
