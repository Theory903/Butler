# Phase 3: Orchestrator & Durable Runtime

> **Status:** Ready for execution  
> **Depends on:** Phase 0 (Foundation), Phase 1 (Auth), Phase 2 (Gateway)  
> **Unlocks:** Phase 4 (Memory + Tools + Search)  
> **Source of truth:** `docs/02-services/orchestrator.md`

---

## Objective

Build the brain of Butler — a durable runtime supervisor that:
- Receives canonical `ButlerEnvelope` from Gateway
- Classifies intent (T0 pattern-match → T1 ML classifier)
- Selects execution mode (Macro / Routine / Durable Workflow)
- Manages task lifecycle with a strict state machine
- Persists all task state in PostgreSQL (survives restarts)
- Keeps hot state in Redis (fast reads)
- Supports approval-gated workflows (pause → approve → resume)
- Runs compensation on failure
- NEVER holds business logic for Memory, Tools, or ML — delegates through contracts

---

## Task State Machine

```
             ┌──────────────────────────────────────────────────────────────┐
             │                  Orchestrator Task Lifecycle                │
             │                                                            │
             │  pending ──▶ planning ──▶ executing ──▶ completed         │
             │     │           │            │             ▲               │
             │     │           ▼            ▼             │               │
             │     │        failed    awaiting_approval ──┘               │
             │     │           ▲            │                             │
             │     │           │            ▼                             │
             │     └───────────┴──── compensating ──▶ compensated        │
             │                              │                             │
             │                              ▼                             │
             │                    compensation_failed                     │
             └──────────────────────────────────────────────────────────────┘
```

---

## Domain Layer: `domain/orchestrator/`

### `domain/orchestrator/models.py` — ORM Models

```python
class Workflow(Base):
    """Workflow = container for related tasks."""
    __tablename__ = "workflows"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)  # macro, routine, durable
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    plan_schema: Mapped[dict] = mapped_column(JSONB, nullable=True)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

class Task(Base):
    """Individual execution unit within a workflow."""
    __tablename__ = "tasks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    parent_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # planning, execution, approval
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    compensation_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

class TaskTransition(Base):
    """Event-sourced trail for task status changes. Partitioned by month."""
    __tablename__ = "task_transitions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)  # auto, manual, timeout, error
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ApprovalRequest(Base):
    """Approval request for gated operations."""
    __tablename__ = "approval_requests"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)  # tool, send, delete
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending, approved, denied, expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
```

### `domain/orchestrator/state.py` — Task State Machine

```python
class TaskStateMachine:
    """Strict state transitions — explicit is better than implicit."""
    
    TRANSITIONS = {
        "pending":              ["planning", "executing", "failed"],
        "planning":             ["executing", "failed"],
        "executing":            ["completed", "awaiting_approval", "failed"],
        "awaiting_approval":    ["executing", "failed", "compensating"],
        "completed":            [],  # Terminal
        "failed":               ["compensating", "pending"],  # Retry allowed
        "compensating":         ["compensated", "compensation_failed"],
        "compensated":          [],  # Terminal
        "compensation_failed":  [],  # Terminal — needs manual intervention
    }
    
    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_status, [])
        return to_status in allowed
    
    @classmethod
    def transition(cls, task: Task, to_status: str, trigger: str, metadata: dict = None) -> TaskTransition:
        """Execute a state transition and create audit trail."""
        if not cls.can_transition(task.status, to_status):
            raise OrchestratorErrors.invalid_transition(task.status, to_status)
        
        transition = TaskTransition(
            task_id=task.id,
            from_status=task.status,
            to_status=to_status,
            trigger=trigger,
            metadata=metadata or {},
        )
        
        task.status = to_status
        if to_status == "executing" and not task.started_at:
            task.started_at = datetime.now(UTC)
        if to_status in ("completed", "failed", "compensated", "compensation_failed"):
            task.completed_at = datetime.now(UTC)
        
        return transition
```

### `domain/orchestrator/contracts.py`

```python
class OrchestratorServiceContract(ABC):
    @abstractmethod
    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        """Main entry — receive envelope, classify, execute, respond."""
    
    @abstractmethod
    async def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get workflow by ID."""
    
    @abstractmethod
    async def approve_request(self, approval_id: str, decision: str) -> Task:
        """Grant or deny an approval request."""
    
    @abstractmethod
    async def get_pending_approvals(self, account_id: str) -> list[ApprovalRequest]:
        """List pending approval requests for an account."""
    
    @abstractmethod
    async def retry_task(self, task_id: str) -> Task:
        """Retry a failed task."""
```

---

## Service Layer: `services/orchestrator/`

### `services/orchestrator/intake.py` — Envelope Processing

```python
class IntakeProcessor:
    """Phase 1: Receive envelope → classify intent → select execution mode."""
    
    def __init__(self, intent_classifier: IntentClassifierContract):
        self._classifier = intent_classifier
    
    async def process(self, envelope: ButlerEnvelope) -> IntakeResult:
        # 1. Classify intent
        intent = await self._classifier.classify(envelope.message)
        
        # 2. Select execution mode
        mode = self._select_mode(intent)
        
        return IntakeResult(
            intent=intent.label,
            confidence=intent.confidence,
            mode=mode,
            requires_tools=intent.requires_tools,
            requires_memory=intent.requires_memory,
        )
    
    def _select_mode(self, intent: IntentResult) -> str:
        """
        Macro = LLM-driven, complex, multi-step.
        Routine = Template-based, deterministic.
        Durable = Long-running, needs persistence.
        """
        if intent.complexity == "simple" and not intent.requires_tools:
            return "routine"
        elif intent.requires_approval or intent.estimated_duration > 30:
            return "durable"
        else:
            return "macro"
```

### `services/orchestrator/planner.py` — Plan Decomposition

```python
class PlanEngine:
    """Decompose intent into executable steps."""
    
    async def create_plan(self, intent: str, context: dict) -> Plan:
        """Create execution plan with ordered steps.
        
        Phase 3: Uses pattern-matching for known intents.
        Phase 5: Uses ML-generated plans for complex intents.
        """
        # Pattern-matched plans for known intents
        plan_templates = {
            "greeting": [Step(action="respond", params={"type": "greeting"})],
            "question": [
                Step(action="memory_recall", params={"type": "context"}),
                Step(action="respond", params={"type": "answer"}),
            ],
            "search": [
                Step(action="search_web", params={}),
                Step(action="extract_evidence", params={}),
                Step(action="respond", params={"type": "search_result"}),
            ],
            "tool_action": [
                Step(action="select_tool", params={}),
                Step(action="execute_tool", params={}),
                Step(action="verify_result", params={}),
                Step(action="respond", params={"type": "tool_result"}),
            ],
        }
        
        steps = plan_templates.get(intent, [
            Step(action="memory_recall", params={}),
            Step(action="respond", params={"type": "general"}),
        ])
        
        return Plan(steps=steps, intent=intent, context=context)
```

### `services/orchestrator/executor.py` — Durable Step Execution

```python
class DurableExecutor:
    """Execute plan steps with durable state persistence.
    
    Every state change is written to PostgreSQL.
    Hot state is cached in Redis for fast reads.
    Tasks survive process restarts.
    """
    
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        state_machine: TaskStateMachine,
    ):
        self._db = db
        self._redis = redis
        self._memory = memory_service
        self._tools = tools_service
        self._sm = state_machine
    
    async def execute_workflow(self, workflow: Workflow, plan: Plan) -> WorkflowResult:
        """Execute all plan steps as durable tasks."""
        results = []
        
        for step in plan.steps:
            task = Task(
                workflow_id=workflow.id,
                task_type=step.action,
                status="pending",
                input_data=step.params,
            )
            self._db.add(task)
            await self._db.flush()
            
            # Cache hot state
            await self._cache_task_state(task)
            
            try:
                # Transition: pending → executing
                transition = self._sm.transition(task, "executing", "auto")
                self._db.add(transition)
                await self._db.flush()
                
                # Execute step
                result = await self._execute_step(task, step, workflow)
                
                # Transition: executing → completed
                task.output_data = result
                transition = self._sm.transition(task, "completed", "auto")
                self._db.add(transition)
                
                results.append(result)
                
            except ApprovalRequired as e:
                # Transition: executing → awaiting_approval
                transition = self._sm.transition(task, "awaiting_approval", "approval_needed")
                self._db.add(transition)
                
                # Create approval request
                approval = ApprovalRequest(
                    task_id=task.id,
                    workflow_id=workflow.id,
                    account_id=workflow.account_id,
                    approval_type=e.approval_type,
                    description=e.description,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
                self._db.add(approval)
                
                # Workflow pauses here — will resume on approval
                break
                
            except Exception as e:
                # Transition: executing → failed
                task.error_data = {"error": str(e), "type": type(e).__name__}
                transition = self._sm.transition(task, "failed", "error")
                self._db.add(transition)
                
                # Check if retryable
                if task.retries < task.max_retries:
                    task.retries += 1
                    transition = self._sm.transition(task, "pending", "retry")
                    self._db.add(transition)
                else:
                    # Start compensation
                    await self._compensate(workflow, results)
                    break
            
            await self._db.commit()
            await self._cache_task_state(task)
        
        workflow.status = "completed" if all(r is not None for r in results) else "failed"
        workflow.completed_at = datetime.now(UTC)
        await self._db.commit()
        
        return WorkflowResult(
            workflow_id=str(workflow.id),
            content=self._build_response(results),
            actions=[r for r in results if r.get("action")],
        )
    
    async def _execute_step(self, task: Task, step: Step, workflow: Workflow) -> dict:
        """Route step to appropriate service."""
        match step.action:
            case "memory_recall":
                return await self._memory.recall(
                    account_id=str(workflow.account_id),
                    query=workflow.context_snapshot.get("message", ""),
                )
            case "search_web":
                return {"action": "search", "status": "executed"}
            case "select_tool" | "execute_tool":
                return await self._tools.execute(
                    tool_name=step.params.get("tool"),
                    params=step.params,
                    account_id=str(workflow.account_id),
                )
            case "verify_result":
                return {"action": "verify", "status": "passed"}
            case "respond":
                return {"action": "respond", "type": step.params.get("type", "general")}
            case _:
                return {"action": step.action, "status": "no_handler"}
    
    async def _compensate(self, workflow: Workflow, completed_results: list):
        """Undo side-effects of completed steps on workflow failure."""
        for result in reversed(completed_results):
            if result.get("compensation"):
                try:
                    await self._tools.compensate(result["compensation"])
                except Exception:
                    logger.error("compensation_failed", workflow_id=str(workflow.id))
    
    async def _cache_task_state(self, task: Task):
        """Cache hot task state in Redis for fast reads."""
        await self._redis.setex(
            f"task:{task.id}:state",
            3600,
            json.dumps({"status": task.status, "type": task.task_type}),
        )
```

### `services/orchestrator/service.py` — Main Orchestrator

```python
class OrchestratorService(OrchestratorServiceContract):
    """Butler's brain — the runtime supervisor."""
    
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        intake: IntakeProcessor,
        planner: PlanEngine,
        executor: DurableExecutor,
    ):
        self._db = db
        self._redis = redis
        self._intake = intake
        self._planner = planner
        self._executor = executor
    
    async def intake(self, envelope: ButlerEnvelope) -> OrchestratorResult:
        """Main entry — the full pipeline."""
        
        # 1. Classify intent
        intake_result = await self._intake.process(envelope)
        
        # 2. Create workflow
        workflow = Workflow(
            account_id=uuid.UUID(envelope.account_id),
            session_id=envelope.session_id,
            intent=intake_result.intent,
            mode=intake_result.mode,
            context_snapshot={"message": envelope.message, "channel": envelope.channel},
        )
        self._db.add(workflow)
        await self._db.flush()
        
        # 3. Create plan
        plan = await self._planner.create_plan(
            intent=intake_result.intent,
            context=workflow.context_snapshot,
        )
        workflow.plan_schema = plan.to_dict()
        
        # 4. Execute
        result = await self._executor.execute_workflow(workflow, plan)
        
        await self._db.commit()
        return result
    
    async def approve_request(self, approval_id: str, decision: str) -> Task:
        """Grant or deny approval, resume task if approved."""
        approval = await self._db.get(ApprovalRequest, uuid.UUID(approval_id))
        if not approval:
            raise OrchestratorErrors.APPROVAL_NOT_FOUND
        
        approval.status = decision  # approved or denied
        approval.decided_at = datetime.now(UTC)
        
        if decision == "approved":
            task = await self._db.get(Task, approval.task_id)
            transition = TaskStateMachine.transition(task, "executing", "approval_granted")
            self._db.add(transition)
            
            # Resume execution
            await self._executor.resume_task(task)
        
        await self._db.commit()
        return task
```

---

## API Layer

### `api/routes/orchestrator.py`

```python
router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    workflow = await svc.get_workflow(workflow_id)
    if not workflow or str(workflow.account_id) != account.account_id:
        raise Problem(type="...", title="Workflow Not Found", status=404)
    return workflow

@router.get("/approvals")
async def list_approvals(
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    return await svc.get_pending_approvals(account.account_id)

@router.post("/approvals/{approval_id}")
async def decide_approval(
    approval_id: str,
    req: ApprovalDecisionRequest,
    account: AccountContext = Depends(get_current_account),
    svc: OrchestratorService = Depends(get_orchestrator_service),
):
    return await svc.approve_request(approval_id, req.decision)
```

---

## Orchestrator Error Definitions

```python
class OrchestratorErrors:
    WORKFLOW_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/workflow-not-found",
        title="Workflow Not Found", status=404,
    )
    APPROVAL_NOT_FOUND = Problem(
        type="https://docs.butler.lasmoid.ai/problems/approval-not-found",
        title="Approval Request Not Found", status=404,
    )
    
    @staticmethod
    def invalid_transition(from_s: str, to_s: str) -> Problem:
        return Problem(
            type="https://docs.butler.lasmoid.ai/problems/invalid-task-transition",
            title="Invalid Task Transition", status=409,
            detail=f"Cannot transition from '{from_s}' to '{to_s}'.",
        )
```

---

## Tests

```python
class TestTaskStateMachine:
    def test_valid_transitions(self):
        assert TaskStateMachine.can_transition("pending", "executing") is True
        assert TaskStateMachine.can_transition("executing", "completed") is True
        assert TaskStateMachine.can_transition("executing", "awaiting_approval") is True
    
    def test_invalid_transitions(self):
        assert TaskStateMachine.can_transition("completed", "pending") is False
        assert TaskStateMachine.can_transition("pending", "completed") is False
    
    def test_transition_creates_audit_trail(self, task):
        transition = TaskStateMachine.transition(task, "executing", "auto")
        assert transition.from_status == "pending"
        assert transition.to_status == "executing"
        assert task.status == "executing"

class TestOrchestratorService:
    async def test_intake_creates_workflow(self, orchestrator, envelope):
        result = await orchestrator.intake(envelope)
        assert result.workflow_id
        assert result.content
    
    async def test_greeting_intent_uses_routine_mode(self, orchestrator, greeting_envelope):
        result = await orchestrator.intake(greeting_envelope)
        workflow = await orchestrator.get_workflow(result.workflow_id)
        assert workflow.mode == "routine"
    
    async def test_approval_pauses_and_resumes(self, orchestrator, tool_envelope):
        result = await orchestrator.intake(tool_envelope)
        approvals = await orchestrator.get_pending_approvals(tool_envelope.account_id)
        assert len(approvals) > 0
        
        await orchestrator.approve_request(str(approvals[0].id), "approved")
        task = await db.get(Task, approvals[0].task_id)
        assert task.status in ("executing", "completed")
```

---

## Verification Checklist

- [ ] `POST /api/v1/chat` → creates Workflow + Tasks in DB
- [ ] Task transitions create audit trail in `task_transitions` table
- [ ] Invalid state transitions raise 409 with RFC 9457
- [ ] Tasks persist in PostgreSQL — survive service restart
- [ ] Hot state readable from Redis
- [ ] Approval request pauses workflow
- [ ] Approval grant resumes execution
- [ ] Failed tasks attempt retry up to `max_retries`
- [ ] Compensation runs on workflow failure

---

*Phase 3 complete → Orchestrator is durable → Phase 4 (Memory + Tools + Search) can begin.*
