# Phase 4: Memory, Tools & Search

> **Status:** Ready for execution  
> **Depends on:** Phase 3 (Orchestrator)  
> **Unlocks:** Phase 5 (ML + Realtime + Communication)  
> **Source of truth:** `docs/02-services/memory.md`, `docs/02-services/tools.md`, `docs/02-services/search.md`

---

## Part A: Memory Service

### Objective

Build an evolving memory engine with:
- **Episodic memory** — conversation turns, interaction traces
- **Entity memory** — named entities with temporal versioning
- **Preference memory** — user preferences with confidence scores
- **Context builder** — assemble relevant context for Orchestrator
- Hybrid retrieval: dense (embeddings) + sparse (keyword) + recency

### Domain Layer: `domain/memory/`

#### `domain/memory/models.py`

```python
class MemoryEntry(Base):
    """Base memory record with temporal metadata."""
    __tablename__ = "memory_entries"
    
    id: Mapped[uuid.UUID]
    account_id: Mapped[uuid.UUID]
    memory_type: Mapped[str]  # episodic, entity, preference, fact
    content: Mapped[dict]     # JSONB — the actual memory payload
    embedding: Mapped[list]   # Vector embedding (pgvector)
    importance: Mapped[float] # 0.0 - 1.0, decay-eligible
    confidence: Mapped[float] # 0.0 - 1.0
    source: Mapped[str]       # conversation, tool_result, observation
    session_id: Mapped[str]
    tags: Mapped[list]        # JSONB array
    valid_from: Mapped[datetime]  # Temporal — when this became true
    valid_until: Mapped[datetime] # Temporal — when this stopped being true
    created_at: Mapped[datetime]
    last_accessed_at: Mapped[datetime]
    access_count: Mapped[int]

class ConversationTurn(Base):
    """Individual conversation turn within a session."""
    __tablename__ = "conversation_turns"
    
    id: Mapped[uuid.UUID]
    account_id: Mapped[uuid.UUID]
    session_id: Mapped[str]
    role: Mapped[str]         # user, assistant, system, tool
    content: Mapped[str]
    turn_index: Mapped[int]
    intent: Mapped[str]
    tool_calls: Mapped[dict]  # JSONB — tools invoked during this turn
    metadata: Mapped[dict]    # JSONB — latency, model, tokens
    created_at: Mapped[datetime]
```

#### `domain/memory/contracts.py`

```python
class MemoryServiceContract(ABC):
    @abstractmethod
    async def store(self, account_id: str, memory_type: str, content: dict, **kwargs) -> MemoryEntry:
        """Store a new memory entry with embedding."""
    
    @abstractmethod
    async def recall(self, account_id: str, query: str, memory_types: list = None, limit: int = 10) -> list[MemoryEntry]:
        """Retrieve relevant memories using hybrid search."""
    
    @abstractmethod
    async def store_turn(self, account_id: str, session_id: str, role: str, content: str, **kwargs) -> ConversationTurn:
        """Store a conversation turn."""
    
    @abstractmethod
    async def get_session_history(self, account_id: str, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        """Get conversation history for a session."""
    
    @abstractmethod
    async def build_context(self, account_id: str, query: str, session_id: str) -> ContextPack:
        """Assemble full context for Orchestrator — session history + relevant memories."""
    
    @abstractmethod
    async def update_entity(self, account_id: str, entity_name: str, facts: dict) -> MemoryEntry:
        """Upsert entity facts with temporal versioning."""
    
    @abstractmethod
    async def set_preference(self, account_id: str, key: str, value: str, confidence: float) -> MemoryEntry:
        """Store or update user preference."""
```

### Service Layer: `services/memory/`

#### `services/memory/retrieval.py` — Hybrid Search

```python
class HybridRetrieval:
    """Dense + sparse + recency retrieval with score fusion."""
    
    async def search(
        self, account_id: str, query: str, memory_types: list = None, limit: int = 10
    ) -> list[ScoredMemory]:
        
        # 1. Dense retrieval (embedding similarity)
        query_embedding = await self._embed(query)
        dense_results = await self._vector_search(account_id, query_embedding, limit * 2)
        
        # 2. Sparse retrieval (keyword match via PostgreSQL FTS)
        sparse_results = await self._keyword_search(account_id, query, limit * 2)
        
        # 3. Recency boost
        recency_results = await self._recent_memories(account_id, limit)
        
        # 4. Reciprocal Rank Fusion
        fused = self._rrf_fusion(dense_results, sparse_results, recency_results)
        
        # 5. Filter by memory type if requested
        if memory_types:
            fused = [m for m in fused if m.memory_type in memory_types]
        
        return fused[:limit]
    
    def _rrf_fusion(self, *result_lists, k: int = 60) -> list[ScoredMemory]:
        """Reciprocal Rank Fusion — combine multiple ranked lists."""
        scores = {}
        for results in result_lists:
            for rank, item in enumerate(results):
                key = str(item.id)
                if key not in scores:
                    scores[key] = {"item": item, "score": 0}
                scores[key]["score"] += 1 / (k + rank + 1)
        
        ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [ScoredMemory(memory=r["item"], score=r["score"]) for r in ranked]
```

#### `services/memory/service.py` — Main Service

```python
class MemoryService(MemoryServiceContract):
    def __init__(self, db: AsyncSession, redis: Redis, embedder: EmbeddingContract, retrieval: HybridRetrieval):
        self._db = db
        self._redis = redis
        self._embedder = embedder
        self._retrieval = retrieval
    
    async def store(self, account_id: str, memory_type: str, content: dict, **kwargs) -> MemoryEntry:
        # Generate embedding for the content
        text_repr = json.dumps(content) if isinstance(content, dict) else str(content)
        embedding = await self._embedder.embed(text_repr)
        
        entry = MemoryEntry(
            account_id=uuid.UUID(account_id),
            memory_type=memory_type,
            content=content,
            embedding=embedding,
            importance=kwargs.get("importance", 0.5),
            confidence=kwargs.get("confidence", 1.0),
            source=kwargs.get("source", "conversation"),
            session_id=kwargs.get("session_id"),
            tags=kwargs.get("tags", []),
            valid_from=datetime.now(UTC),
        )
        self._db.add(entry)
        await self._db.commit()
        return entry
    
    async def build_context(self, account_id: str, query: str, session_id: str) -> ContextPack:
        """Core method — assembles everything the Orchestrator needs."""
        # 1. Recent session history
        history = await self.get_session_history(account_id, session_id, limit=20)
        
        # 2. Relevant memories (hybrid search)
        memories = await self.recall(account_id, query, limit=10)
        
        # 3. Active preferences
        preferences = await self._get_active_preferences(account_id)
        
        # 4. Relevant entities
        entities = await self.recall(account_id, query, memory_types=["entity"], limit=5)
        
        return ContextPack(
            session_history=history,
            relevant_memories=memories,
            preferences=preferences,
            entities=entities,
            context_token_budget=4096,  # Configurable
        )
```

---

## Part B: Tools Service

### Objective

Build the capability control plane that:
- Registers tools with risk tiers and policies
- Executes tools in sandboxed environments with timeouts
- Verifies pre/post conditions
- Enforces idempotency for side-effecting tools
- Tracks compensation handlers for undo
- Produces audit trail for every execution

### Domain Layer: `domain/tools/`

#### `domain/tools/models.py`

```python
class ToolDefinition(Base):
    """Tool registry entry — defines what a tool CAN do."""
    __tablename__ = "tool_definitions"
    
    id: Mapped[uuid.UUID]
    name: Mapped[str]            # unique tool name
    description: Mapped[str]
    category: Mapped[str]        # search, communication, device, data
    risk_tier: Mapped[str]       # T0_safe, T1_low, T2_medium, T3_high
    input_schema: Mapped[dict]   # JSON Schema for parameters
    output_schema: Mapped[dict]  # JSON Schema for results
    requires_approval: Mapped[bool]
    idempotent: Mapped[bool]
    timeout_seconds: Mapped[int]
    compensation_handler: Mapped[str]  # Name of undo tool
    enabled: Mapped[bool]
    version: Mapped[str]

class ToolExecution(Base):
    """Audit record of every tool invocation."""
    __tablename__ = "tool_executions"
    
    id: Mapped[uuid.UUID]
    tool_name: Mapped[str]
    account_id: Mapped[uuid.UUID]
    task_id: Mapped[uuid.UUID]
    workflow_id: Mapped[uuid.UUID]
    input_params: Mapped[dict]
    output_result: Mapped[dict]
    risk_tier: Mapped[str]
    status: Mapped[str]           # pending, executing, completed, failed, compensated
    idempotency_key: Mapped[str]
    verification_passed: Mapped[bool]
    duration_ms: Mapped[int]
    error_data: Mapped[dict]
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime]
```

#### `domain/tools/contracts.py`

```python
class ToolsServiceContract(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, params: dict, account_id: str, **kwargs) -> ToolResult:
        """Execute a tool with verification and audit."""
    
    @abstractmethod
    async def compensate(self, compensation_ref: dict) -> bool:
        """Run compensation handler to undo a tool's side-effects."""
    
    @abstractmethod
    async def get_tool(self, name: str) -> ToolDefinition | None:
        """Get tool definition by name."""
    
    @abstractmethod
    async def list_tools(self, category: str = None) -> list[ToolDefinition]:
        """List available tools, optionally filtered by category."""
    
    @abstractmethod
    async def validate_params(self, tool_name: str, params: dict) -> ValidationResult:
        """Validate tool parameters against schema."""
```

### Service Layer: `services/tools/`

#### `services/tools/executor.py`

```python
class ToolExecutor:
    """Sandboxed tool execution with timeout, verification, and audit."""
    
    async def execute(
        self,
        tool: ToolDefinition,
        params: dict,
        account_id: str,
        task_id: str = None,
        idempotency_key: str = None,
    ) -> ToolResult:
        
        # 1. Idempotency check
        if idempotency_key:
            cached = await self._check_idempotent(idempotency_key)
            if cached:
                return cached
        
        # 2. Pre-execution verification
        pre_check = await self._verify_preconditions(tool, params, account_id)
        if not pre_check.passed:
            raise ToolErrors.precondition_failed(pre_check.reason)
        
        # 3. Check approval requirement
        if tool.requires_approval:
            raise ApprovalRequired(
                approval_type="tool_execution",
                description=f"Tool '{tool.name}' requires approval",
            )
        
        # 4. Create execution record
        execution = ToolExecution(
            tool_name=tool.name,
            account_id=uuid.UUID(account_id),
            task_id=uuid.UUID(task_id) if task_id else None,
            input_params=params,
            risk_tier=tool.risk_tier,
            status="executing",
            idempotency_key=idempotency_key,
        )
        self._db.add(execution)
        await self._db.flush()
        
        # 5. Execute with timeout
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_tool(tool, params),
                timeout=tool.timeout_seconds,
            )
            duration = int((time.monotonic() - start) * 1000)
            
            # 6. Post-execution verification
            post_check = await self._verify_postconditions(tool, params, result)
            
            execution.output_result = result
            execution.status = "completed"
            execution.verification_passed = post_check.passed
            execution.duration_ms = duration
            execution.completed_at = datetime.now(UTC)
            
            await self._db.commit()
            
            # 7. Cache for idempotency
            if idempotency_key:
                await self._cache_idempotent(idempotency_key, result)
            
            return ToolResult(
                success=True,
                data=result,
                tool_name=tool.name,
                execution_id=str(execution.id),
                verification=post_check,
                compensation={"handler": tool.compensation_handler, "execution_id": str(execution.id)} if tool.compensation_handler else None,
            )
            
        except asyncio.TimeoutError:
            execution.status = "failed"
            execution.error_data = {"error": "timeout", "timeout_s": tool.timeout_seconds}
            await self._db.commit()
            raise ToolErrors.timeout(tool.name, tool.timeout_seconds)
```

#### `services/tools/verification.py`

```python
class ToolVerifier:
    """Pre/post execution verification for tools."""
    
    async def verify_preconditions(self, tool: ToolDefinition, params: dict, account_id: str) -> VerificationResult:
        """Check before execution."""
        checks = []
        
        # 1. Schema validation
        schema_valid = self._validate_schema(tool.input_schema, params)
        checks.append(("schema", schema_valid))
        
        # 2. Permission check
        has_permission = await self._check_permission(tool, account_id)
        checks.append(("permission", has_permission))
        
        # 3. Risk tier check
        risk_ok = self._check_risk_tier(tool.risk_tier, account_id)
        checks.append(("risk_tier", risk_ok))
        
        passed = all(ok for _, ok in checks)
        return VerificationResult(passed=passed, checks=checks)
    
    async def verify_postconditions(self, tool: ToolDefinition, params: dict, result: dict) -> VerificationResult:
        """Check after execution — did the tool actually do what it says?"""
        checks = []
        
        # 1. Output schema validation
        if tool.output_schema:
            schema_valid = self._validate_schema(tool.output_schema, result)
            checks.append(("output_schema", schema_valid))
        
        # 2. Side-effect verification (tool-specific)
        side_effect_ok = await self._verify_side_effects(tool.name, params, result)
        checks.append(("side_effects", side_effect_ok))
        
        passed = all(ok for _, ok in checks)
        return VerificationResult(passed=passed, checks=checks)
```

---

## Part C: Search Service

### Objective

Build the evidence engine that:
- Understands and rewrites queries
- Routes to appropriate providers (Google, Crawl4AI, direct fetch)
- Extracts clean content from web pages
- Packages evidence with citations and freshness metadata

### Service Layer: `services/search/`

#### `services/search/service.py`

```python
class SearchService:
    """Evidence engine — retrieve, extract, cite."""
    
    async def search(self, query: str, mode: str = "auto", **kwargs) -> EvidencePack:
        # 1. Query understanding
        processed = await self._query_processor.process(query)
        
        # 2. Provider routing
        if mode == "auto":
            mode = self._select_mode(processed)
        
        # 3. Execute search
        raw_results = await self._provider_router.search(processed.rewritten_query, mode)
        
        # 4. Content extraction
        extracted = []
        for result in raw_results[:5]:  # Top 5
            content = await self._extractor.extract(result.url)
            extracted.append(ExtractedContent(
                url=result.url,
                title=result.title,
                content=content.text[:2000],  # Truncate
                extraction_method=content.method,
                freshness=result.published_date,
            ))
        
        # 5. Package evidence
        return EvidencePack(
            query=query,
            mode=mode,
            results=extracted,
            citations=self._build_citations(extracted),
            result_count=len(extracted),
        )
```

#### `services/search/extraction.py`

```python
class ContentExtractor:
    """Extract clean text from web pages."""
    
    async def extract(self, url: str) -> ExtractionResult:
        # Primary: Trafilatura
        try:
            html = await self._fetch(url)
            text = trafilatura.extract(html, include_links=True, include_tables=True)
            if text and len(text) > 100:
                return ExtractionResult(text=text, method="trafilatura")
        except Exception:
            pass
        
        # Fallback: BeautifulSoup
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return ExtractionResult(text=text, method="beautifulsoup")
        except Exception:
            return ExtractionResult(text="", method="failed")
```

---

## API Routes

```python
# api/routes/memory.py
router = APIRouter(prefix="/memory", tags=["memory"])

@router.post("/store")
async def store_memory(req: StoreMemoryRequest, account=Depends(get_current_account), svc=Depends(get_memory)):
    return await svc.store(account.account_id, req.memory_type, req.content, **req.kwargs)

@router.post("/recall")
async def recall(req: RecallRequest, account=Depends(get_current_account), svc=Depends(get_memory)):
    return await svc.recall(account.account_id, req.query, req.memory_types, req.limit)

@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str, account=Depends(get_current_account), svc=Depends(get_memory)):
    return await svc.get_session_history(account.account_id, session_id)

# api/routes/tools.py
router = APIRouter(prefix="/tools", tags=["tools"])

@router.get("/")
async def list_tools(category: str = None, svc=Depends(get_tools)):
    return await svc.list_tools(category)

@router.post("/{tool_name}/execute")
async def execute_tool(tool_name: str, req: ExecuteToolRequest, account=Depends(get_current_account), svc=Depends(get_tools)):
    return await svc.execute(tool_name, req.params, account.account_id, idempotency_key=req.idempotency_key)

# api/routes/search.py
router = APIRouter(prefix="/search", tags=["search"])

@router.post("/")
async def search(req: SearchRequest, account=Depends(get_current_account), svc=Depends(get_search)):
    return await svc.search(req.query, req.mode)
```

---

## Dependencies to Add

```toml
trafilatura = ">=1.9"
beautifulsoup4 = ">=4.12"
pgvector = ">=0.2"           # Vector operations in PostgreSQL
numpy = ">=1.26"             # Embedding calculations
jsonschema = ">=4.21"        # Tool param validation
```

---

## Verification Checklist

### Memory
- [ ] Store memory → retrieve by hybrid search
- [ ] Session history persists across requests
- [ ] Context builder returns combined session + memory + preferences
- [ ] Entity upsert handles temporal versioning

### Tools
- [ ] Tool execution creates audit record
- [ ] Timeout enforcement stops hung tools
- [ ] Idempotency key prevents duplicate execution
- [ ] Pre/post verification runs for every execution
- [ ] Approval-required tools raise `ApprovalRequired`

### Search
- [ ] Query → provider → extract → evidence pack pipeline works
- [ ] Trafilatura extraction produces clean text
- [ ] Citations include URL, title, freshness

---

*Phase 4 complete → Butler can remember, act, and search → Phase 5 (ML + Realtime + Communication) can begin.*
