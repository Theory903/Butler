# Phase 5: ML, Realtime & Communication

> **Status:** Ready for execution  
> **Depends on:** Phase 4 (Memory + Tools + Search)  
> **Unlocks:** Phase 6 (Security + Observability)  
> **Source of truth:** `docs/02-services/ml.md`, `docs/02-services/realtime.md`, `docs/02-services/communication.md`

---

## Part A: ML Service

### Objective

Build the intelligence platform providing:
- **Intent classifier** — Tiered (T0 pattern-match → T1 lightweight → T2 ML model)
- **Embedding engine** — Dense text embeddings for Memory service
- **Model registry** — Version tracking and configuration
- **Feature store** — Online feature serving for context-aware decisions

### Service Layer: `services/ml/`

#### `services/ml/intent.py` — Tiered Intent Classifier

```python
class IntentClassifier:
    """Tiered intent classification: fast patterns → lightweight ML → full model."""
    
    # T0: Pattern matching (zero latency)
    PATTERN_INTENTS = {
        "greeting": ["hello", "hi", "hey", "good morning", "good evening"],
        "farewell": ["bye", "goodbye", "see you", "talk later"],
        "thanks": ["thank you", "thanks", "appreciate it"],
        "help": ["help", "what can you do", "how do you work"],
        "status": ["what's happening", "status update", "any updates"],
    }
    
    async def classify(self, text: str) -> IntentResult:
        # T0: Regex/pattern match
        t0_result = self._pattern_match(text)
        if t0_result and t0_result.confidence >= 0.9:
            return t0_result
        
        # T1: Lightweight keyword classifier
        t1_result = self._keyword_classify(text)
        if t1_result and t1_result.confidence >= 0.8:
            return t1_result
        
        # T2: ML model (when available in Phase 5+)
        # For now, fallback to keyword with lower confidence
        return t1_result or IntentResult(
            label="general",
            confidence=0.5,
            complexity="simple",
            requires_tools=False,
            requires_memory=True,
        )
    
    def _pattern_match(self, text: str) -> IntentResult | None:
        text_lower = text.lower().strip()
        for intent, patterns in self.PATTERN_INTENTS.items():
            if any(p in text_lower for p in patterns):
                return IntentResult(label=intent, confidence=0.95, complexity="simple")
        return None
    
    def _keyword_classify(self, text: str) -> IntentResult | None:
        keywords = {
            "search": (["search", "find", "look up", "what is", "who is"], "search", True),
            "weather": (["weather", "temperature", "forecast"], "search", True),
            "reminder": (["remind", "reminder", "don't forget"], "tool_action", True),
            "send": (["send", "email", "message", "text"], "tool_action", True),
            "schedule": (["schedule", "calendar", "meeting"], "tool_action", True),
            "remember": (["remember", "note", "save"], "memory_write", False),
        }
        
        text_lower = text.lower()
        for intent, (kws, complexity, needs_tools) in keywords.items():
            if any(kw in text_lower for kw in kws):
                return IntentResult(
                    label=intent, confidence=0.75, complexity=complexity,
                    requires_tools=needs_tools, requires_memory=True,
                )
        return None
```

#### `services/ml/embeddings.py` — Embedding Engine

```python
class EmbeddingService:
    """Dense text embeddings for Memory retrieval.
    
    Phase 5 initial: Uses sentence-transformers locally.
    Production: BGE-M3 or similar model.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None  # Lazy load
    
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if not self._model:
            await self._load_model()
        
        # Run embedding in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None, self._model.encode, text
        )
        return embedding.tolist()
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding for efficiency."""
        if not self._model:
            await self._load_model()
        
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self._model.encode, texts
        )
        return [e.tolist() for e in embeddings]
    
    async def _load_model(self):
        """Lazy load model on first use."""
        from sentence_transformers import SentenceTransformer
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None, SentenceTransformer, self._model_name
        )
```

#### `services/ml/registry.py` — Model Registry

```python
class ModelRegistry:
    """Track available models, versions, and configurations."""
    
    MODELS = {
        "intent-classifier-t0": {
            "type": "pattern",
            "version": "1.0.0",
            "status": "active",
        },
        "intent-classifier-t1": {
            "type": "keyword",
            "version": "1.0.0",
            "status": "active",
        },
        "embeddings-minilm": {
            "type": "sentence-transformer",
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384,
            "version": "1.0.0",
            "status": "active",
        },
    }
    
    def get_active_model(self, task: str) -> dict | None:
        return self.MODELS.get(task)
    
    def list_models(self) -> list[dict]:
        return [{"name": k, **v} for k, v in self.MODELS.items()]
```

### API Routes: `api/routes/ml.py`

```python
router = APIRouter(prefix="/ml", tags=["ml"])

@router.post("/intent/classify")
async def classify_intent(req: ClassifyRequest, svc=Depends(get_ml)):
    return await svc.classify_intent(req.text)

@router.post("/embed")
async def embed_text(req: EmbedRequest, svc=Depends(get_ml)):
    return await svc.embed(req.text)

@router.get("/models")
async def list_models(svc=Depends(get_ml)):
    return svc.list_models()
```

---

## Part B: Realtime Service

### Objective

Build the session stream platform that:
- Manages WebSocket connections with ticket-based auth
- Streams typed events (workflow updates, approvals, responses)
- Tracks presence (connected, idle, active device)
- Supports cursor-based resume on reconnection
- Separates durable (Redis Streams) vs ephemeral (Pub/Sub) events

### Service Layer: `services/realtime/`

#### `services/realtime/manager.py` — Connection Manager

```python
class ConnectionManager:
    """WebSocket connection lifecycle management."""
    
    def __init__(self, redis: Redis):
        self._connections: dict[str, WebSocket] = {}  # account_id → websocket
        self._redis = redis
    
    async def connect(self, websocket: WebSocket, account_id: str, session_id: str):
        """Accept connection and register."""
        await websocket.accept()
        self._connections[account_id] = websocket
        
        # Update presence
        await self._redis.hset(f"presence:{account_id}", mapping={
            "status": "connected",
            "session_id": session_id,
            "connected_at": datetime.now(UTC).isoformat(),
            "device_id": websocket.headers.get("X-Device-ID", "unknown"),
        })
        await self._redis.expire(f"presence:{account_id}", 3600)
    
    async def disconnect(self, account_id: str):
        """Remove connection and update presence."""
        self._connections.pop(account_id, None)
        await self._redis.hset(f"presence:{account_id}", "status", "disconnected")
    
    async def send_event(self, account_id: str, event: RealtimeEvent):
        """Send typed event to connected client."""
        ws = self._connections.get(account_id)
        if ws:
            try:
                await ws.send_json(event.to_dict())
            except WebSocketDisconnect:
                await self.disconnect(account_id)
        
        # Always persist durable events for replay
        if event.durable:
            await self._redis.xadd(
                f"events:{account_id}",
                event.to_dict(),
                maxlen=1000,
            )
    
    async def broadcast_to_account(self, account_id: str, event: RealtimeEvent):
        """Send to all devices for an account."""
        await self.send_event(account_id, event)
```

#### `services/realtime/events.py` — Event Types

```python
class RealtimeEvent(BaseModel):
    """Typed event for real-time delivery."""
    event_type: str           # workflow.update, approval.request, response.chunk, presence.change
    payload: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    durable: bool = True      # If true, persisted in Redis Streams for replay
    
    def to_dict(self):
        return {
            "type": self.event_type,
            "payload": json.dumps(self.payload),
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
        }

# Event factory helpers
class Events:
    @staticmethod
    def workflow_update(workflow_id: str, status: str, detail: str = None) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="workflow.update",
            payload={"workflow_id": workflow_id, "status": status, "detail": detail},
        )
    
    @staticmethod
    def approval_request(approval_id: str, description: str) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="approval.request",
            payload={"approval_id": approval_id, "description": description},
        )
    
    @staticmethod
    def response_chunk(content: str, final: bool = False) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="response.chunk",
            payload={"content": content, "final": final},
            durable=False,  # Ephemeral — no replay needed
        )
    
    @staticmethod
    def presence_change(account_id: str, status: str) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="presence.change",
            payload={"account_id": account_id, "status": status},
            durable=False,
        )
```

#### `services/realtime/presence.py`

```python
class PresenceService:
    """Track connection presence per account/device."""
    
    async def get_presence(self, account_id: str) -> PresenceInfo:
        data = await self._redis.hgetall(f"presence:{account_id}")
        if not data:
            return PresenceInfo(status="offline")
        return PresenceInfo(**data)
    
    async def set_idle(self, account_id: str):
        await self._redis.hset(f"presence:{account_id}", "status", "idle")
    
    async def heartbeat(self, account_id: str):
        """Client sends periodic heartbeat to keep connection alive."""
        await self._redis.hset(f"presence:{account_id}", mapping={
            "status": "connected",
            "last_heartbeat": datetime.now(UTC).isoformat(),
        })
        await self._redis.expire(f"presence:{account_id}", 300)  # 5 min timeout
```

### API Routes: `api/routes/realtime.py`

```python
router = APIRouter(prefix="/realtime", tags=["realtime"])

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),  # Ticket-based auth
    manager: ConnectionManager = Depends(get_connection_manager),
    auth: JWTAuthMiddleware = Depends(get_auth_middleware),
):
    """WebSocket endpoint with ticket authentication."""
    # Verify ticket (single-use token for WS upgrade)
    account = await auth.authenticate(f"Bearer {token}")
    
    await manager.connect(websocket, account.account_id, account.session_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "heartbeat":
                await manager._presence.heartbeat(account.account_id)
            elif data.get("type") == "resume":
                # Replay events from cursor
                cursor = data.get("cursor", "0")
                events = await manager._redis.xrange(f"events:{account.account_id}", min=cursor)
                for event_id, event_data in events:
                    await websocket.send_json({"event_id": event_id, **event_data})
    except WebSocketDisconnect:
        await manager.disconnect(account.account_id)

@router.get("/presence/{account_id}")
async def get_presence(account_id: str, presence=Depends(get_presence)):
    return await presence.get_presence(account_id)
```

---

## Part C: Communication Service

### Objective

Build the policy-governed delivery runtime that:
- Enforces consent, quiet hours, and rate limits per channel
- Routes messages through channel-specific providers
- Manages delivery with priority queues and retry policies
- Handles webhook ingestion for delivery receipts
- Tracks delivery state per message

### Service Layer: `services/communication/`

#### `services/communication/policy.py`

```python
class CommunicationPolicy:
    """Policy layer — consent, quiet hours, rate limits."""
    
    async def evaluate(self, request: DeliveryRequest) -> PolicyDecision:
        checks = []
        
        # 1. Consent check
        consent = await self._check_consent(request.account_id, request.channel)
        checks.append(("consent", consent))
        
        # 2. Quiet hours check
        quiet = self._check_quiet_hours(request.account_id, request.channel)
        checks.append(("quiet_hours", quiet))
        
        # 3. Rate limit per channel
        rate = await self._check_channel_rate(request.account_id, request.channel)
        checks.append(("rate_limit", rate))
        
        # 4. Sender verification
        sender = await self._verify_sender(request.sender_id, request.channel)
        checks.append(("sender_verified", sender))
        
        allowed = all(ok for _, ok in checks)
        return PolicyDecision(
            allowed=allowed,
            checks=checks,
            blocked_reason=next((name for name, ok in checks if not ok), None),
        )
```

#### `services/communication/delivery.py`

```python
class DeliveryService:
    """Multi-channel message delivery with retry."""
    
    PROVIDERS = {
        "sms": "twilio",
        "email": "sendgrid",
        "push": "fcm",
        "whatsapp": "twilio",
    }
    
    async def send(self, request: DeliveryRequest) -> DeliveryResult:
        # 1. Policy check
        decision = await self._policy.evaluate(request)
        if not decision.allowed:
            raise CommunicationErrors.policy_blocked(decision.blocked_reason)
        
        # 2. Create delivery record
        delivery = DeliveryRecord(
            account_id=request.account_id,
            channel=request.channel,
            recipient=request.recipient,
            content=request.content,
            priority=request.priority,
            status="queued",
            idempotency_key=request.idempotency_key,
        )
        self._db.add(delivery)
        await self._db.flush()
        
        # 3. Route to provider
        provider = self._get_provider(request.channel)
        
        try:
            result = await provider.send(request)
            delivery.status = "delivered"
            delivery.provider_id = result.provider_id
        except ProviderError as e:
            delivery.status = "failed"
            delivery.error = str(e)
            delivery.retry_count += 1
            
            if delivery.retry_count < delivery.max_retries:
                delivery.status = "retry_scheduled"
                await self._schedule_retry(delivery)
        
        await self._db.commit()
        return DeliveryResult(delivery_id=str(delivery.id), status=delivery.status)
```

### API Routes: `api/routes/communication.py`

```python
router = APIRouter(prefix="/communication", tags=["communication"])

@router.post("/send")
async def send_message(req: SendRequest, account=Depends(get_current_account), svc=Depends(get_communication)):
    return await svc.send(DeliveryRequest(account_id=account.account_id, **req.dict()))

@router.get("/deliveries")
async def list_deliveries(account=Depends(get_current_account), svc=Depends(get_communication)):
    return await svc.list_deliveries(account.account_id)

@router.post("/webhooks/{provider}")
async def webhook_ingress(provider: str, request: Request, svc=Depends(get_communication)):
    payload = await request.json()
    signature = request.headers.get("X-Webhook-Signature")
    return await svc.process_webhook(provider, payload, signature)
```

---

## Dependencies to Add

```toml
sentence-transformers = ">=2.6"     # Embedding engine
websockets = ">=12.0"               # WebSocket support (built into FastAPI)
```

---

## Verification Checklist

### ML
- [ ] Pattern intent classifier returns correct labels
- [ ] Embedding service generates vectors of expected dimension
- [ ] Model registry lists available models

### Realtime
- [ ] WebSocket connects with ticket auth
- [ ] Events stream to connected clients
- [ ] Durable events persist in Redis Streams
- [ ] Resume from cursor replays missed events
- [ ] Presence updates on connect/disconnect/heartbeat

### Communication
- [ ] Policy blocks without consent
- [ ] Quiet hours enforcement works
- [ ] Delivery record created for every send
- [ ] Retry scheduled on provider failure

---

*Phase 5 complete → Butler has intelligence, live streaming, and messaging → Phase 6 (hardening) can begin.*
