# Phase 6: Security, Observability & Ambient Intelligence

> **Status:** Ready for execution  
> **Depends on:** Phase 5 (ML + Realtime + Communication)  
> **Unlocks:** Production readiness  
> **Source of truth:** `docs/02-services/security.md`, `docs/02-services/observability.md`, `docs/02-services/device.md`, `docs/02-services/vision.md`, `docs/02-services/audio.md`

---

## Part A: Security Service

### Objective

Build Butler's model-safety and agent-control layer:
- **Trust classification** — classify every input by trust level
- **Channel separation** — never merge untrusted content into instruction authority
- **Content defense** — injection detection with pattern + trust scoring
- **Policy Decision Point** — OPA-compatible allow/deny evaluation
- **Tool capability gates** — scoped capabilities with approval classes
- **Memory isolation** — purpose-bound retrieval with redaction
- **Cryptography** — AES-256-GCM encryption, key hierarchy

### Service Layer: `services/security/`

#### `services/security/trust.py` — Trust Classification

```python
from enum import Enum

class TrustLevel(str, Enum):
    TRUSTED = "trusted"         # System policy, instructions
    INTERNAL = "internal"       # Butler services, workload identity
    USER_INPUT = "user_input"   # Direct user requests
    RETRIEVED = "retrieved"     # Memory, knowledge base
    EXTERNAL = "external"       # Web, OCR, documents, email
    UNTRUSTED = "untrusted"     # User uploads, unknown sources

SOURCE_TRUST_MAP = {
    "system_policy": TrustLevel.TRUSTED,
    "workload_internal": TrustLevel.INTERNAL,
    "user_direct_input": TrustLevel.USER_INPUT,
    "memory_episodic": TrustLevel.RETRIEVED,
    "memory_entity": TrustLevel.RETRIEVED,
    "web_content": TrustLevel.EXTERNAL,
    "ocr_output": TrustLevel.EXTERNAL,
    "document_upload": TrustLevel.EXTERNAL,
    "email_body": TrustLevel.EXTERNAL,
    "screenshot_vision": TrustLevel.EXTERNAL,
    "camera_scene_text": TrustLevel.EXTERNAL,
}

class TrustClassifier:
    """Classify every input source by trust level."""
    
    def classify(self, source_type: str) -> TrustLevel:
        return SOURCE_TRUST_MAP.get(source_type, TrustLevel.UNTRUSTED)
    
    def classify_content(self, content: str, source_type: str) -> ContentSource:
        return ContentSource(
            source_type=source_type,
            trust_level=self.classify(source_type),
            content_class=self._detect_content_class(content),
            classification_reason=f"Source type: {source_type}",
        )

class ChannelSeparator:
    """Route content to appropriate channel — NEVER merge untrusted into instructions."""
    
    CHANNELS = {
        "instructions": {"trust": TrustLevel.TRUSTED, "sources": ["system_policy", "builtin_instructions"]},
        "data_context": {"trust": TrustLevel.EXTERNAL, "sources": ["web_content", "ocr_output", "document_upload"]},
        "memory_context": {"trust": TrustLevel.RETRIEVED, "sources": ["memory_episodic", "memory_entity"]},
        "tool_specs": {"trust": TrustLevel.INTERNAL, "sources": ["tool_registry"]},
        "policy_constraints": {"trust": TrustLevel.TRUSTED, "sources": ["security_policy"]},
    }
    
    def route_to_channel(self, source: ContentSource) -> str:
        for channel, config in self.CHANNELS.items():
            if source.source_type in config["sources"]:
                return channel
        return "data_context"  # Default to lowest trust
```

#### `services/security/defense.py` — Content Defense

```python
class ContentDefense:
    """Multi-signal injection detection — pattern matching is ONE weak signal, not religion."""
    
    DETECTION_SIGNALS = {
        "ignore_instructions": ["ignore previous", "disregard", "forget instructions"],
        "role_confusion": ["you are now", "pretend to be", "roleplay as"],
        "context_injection": ["in the text above", "as mentioned before"],
        "channel_escalation": ["system prompt", "hidden instructions"],
        "tool_injection": ["execute", "run command", "shell", "bash"],
        "obfuscation": ["base64", "hex encoding", "url encoding"],
    }
    
    RESPONSE_ACTIONS = {
        "tag_suspicious": "Content marked untrusted",
        "lower_trust": "Trust score reduced",
        "exclude_high_authority": "Blocked from instruction channel",
        "require_approval": "Human approval required",
        "quarantine": "Security event logged, content isolated",
        "block": "High-confidence attack blocked",
    }
    
    async def evaluate(self, content: str, source: ContentSource) -> DefenseDecision:
        # 1. Base trust from source
        trust = self._get_base_trust(source)
        
        # 2. Pattern detection (weak signal)
        signals = self._detect_injection_patterns(content)
        
        # 3. Adjust trust
        if signals:
            trust *= 0.5
        
        # 4. Decide channel assignment
        if trust < 0.3:
            channel = "quarantine"
            block = True
        elif trust < 0.6:
            channel = "data_context"
        else:
            channel = ChannelSeparator().route_to_channel(source)
            block = False
        
        return DefenseDecision(
            trust_score=trust,
            channel_assignment=channel,
            response_action=self._decide_response(trust, signals),
            suspicious_signals=signals,
            block=block,
        )
    
    def _detect_injection_patterns(self, content: str) -> list[str]:
        content_lower = content.lower()
        found = []
        for signal_type, patterns in self.DETECTION_SIGNALS.items():
            if any(p in content_lower for p in patterns):
                found.append(signal_type)
        return found
    
    def _get_base_trust(self, source: ContentSource) -> float:
        trust_scores = {
            TrustLevel.TRUSTED: 1.0,
            TrustLevel.INTERNAL: 0.95,
            TrustLevel.USER_INPUT: 0.8,
            TrustLevel.RETRIEVED: 0.7,
            TrustLevel.EXTERNAL: 0.5,
            TrustLevel.UNTRUSTED: 0.2,
        }
        return trust_scores.get(source.trust_level, 0.2)
```

#### `services/security/policy.py` — Policy Decision Point

```python
class PolicyDecisionPoint:
    """OPA-compatible policy evaluation engine.
    
    Phase 6 initial: Python-based policy evaluation.
    Production: Can be backed by OPA server.
    """
    
    async def evaluate(self, input: PolicyInput) -> PolicyDecision:
        """Evaluate policy for an action request."""
        
        # Deny untrusted content in planning
        if input.content_trust_level == "untrusted" and input.action == "plan:create":
            return PolicyDecision(allow=False, reason="Untrusted content cannot create plans")
        
        # Financial actions require step-up auth
        if input.action.startswith("financial:") and input.assurance_level != "aal2":
            return PolicyDecision(
                allow=False,
                reason="Financial actions require AAL2",
                obligations=["require_step_up"],
            )
        
        # Physical device control requires explicit approval
        if input.action.startswith("device:") and input.action != "device:view":
            if input.approval_state != "approved":
                return PolicyDecision(
                    allow=False,
                    reason="Device control requires approval",
                    obligations=["require_approval"],
                )
        
        # External communication requires approval
        if input.action.startswith("communication:"):
            if input.approval_state != "approved":
                return PolicyDecision(
                    allow=False,
                    reason="External communication requires approval",
                    obligations=["require_approval"],
                )
        
        # Allow safe reads
        if input.action.endswith(":read") and input.content_trust_level != "untrusted":
            return PolicyDecision(allow=True, reason="Safe read allowed")
        
        # Default: allow with logging
        return PolicyDecision(allow=True, reason="Default allow")

class ToolCapabilityGate:
    """Scoped capability validation for tool execution."""
    
    async def validate(self, request: ToolGateRequest, actor: ActorContext) -> ToolGateDecision:
        # 1. Check capability scope exists
        capability = self._capabilities.get(request.scope)
        if not capability:
            return ToolGateDecision(allowed=False, reason="Unknown capability scope")
        
        # 2. Check credential mode
        if not self._check_credential(actor, capability.credential_mode):
            return ToolGateDecision(allowed=False, reason="Invalid credential mode")
        
        # 3. Check approval requirement
        if capability.approval_class == "explicit" and not request.approval_token:
            return ToolGateDecision(allowed=False, reason="Requires approval", requires_approval=True)
        
        # 4. Check idempotency for side effects
        if capability.side_effect_class != "read" and capability.idempotency_required:
            if not request.idempotency_key:
                return ToolGateDecision(allowed=False, reason="Idempotency key required")
        
        return ToolGateDecision(allowed=True)

class MemoryIsolation:
    """Purpose-bound memory retrieval with access classes."""
    
    MEMORY_POLICIES = {
        "public_profile": {"min_assurance": "aal1", "raw_access": True, "redaction": False},
        "preferences": {"min_assurance": "aal1", "raw_access": True, "redaction": False},
        "communication": {"min_assurance": "aal1", "raw_access": False, "redaction": True},
        "auth_security": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "financial": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "health": {"min_assurance": "aal2", "raw_access": False, "redaction": True},
        "restricted": {"min_assurance": "aal3", "raw_access": False, "redaction": True},
    }
    
    async def check_retrieval(self, memory_class: str, task_family: str, assurance: str) -> RetrievalDecision:
        policy = self.MEMORY_POLICIES.get(memory_class)
        if not policy:
            return RetrievalDecision(allowed=False, reason="Unknown memory class")
        
        # Check assurance level
        assurance_order = {"aal1": 1, "aal2": 2, "aal3": 3}
        if assurance_order.get(assurance, 0) < assurance_order.get(policy["min_assurance"], 3):
            return RetrievalDecision(allowed=False, reason="Assurance level too low")
        
        access_mode = "raw" if policy["raw_access"] else "summarized"
        return RetrievalDecision(
            allowed=True,
            access_mode=access_mode,
            redaction_required=policy["redaction"],
        )
```

#### `services/security/crypto.py` — Cryptography Utilities

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class AESCipher:
    """AES-256-GCM with versioning and AAD per security.md spec."""
    
    VERSION = b"\x01"
    
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self._aesgcm = AESGCM(key)
    
    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, self.VERSION + aad)
        return self.VERSION + nonce + ciphertext
    
    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        version = blob[:1]
        if version != self.VERSION:
            raise ValueError("Unsupported ciphertext version")
        nonce = blob[1:13]
        ciphertext = blob[13:]
        return self._aesgcm.decrypt(nonce, ciphertext, version + aad)

class KeyHierarchy:
    """Three-level key hierarchy: Root (KMS) → Domain KEKs → Data DEKs."""
    
    DOMAIN_KEKS = {
        "credentials": "kek_cred_v1",
        "user_secrets": "kek_user_v1",
        "memory_pii": "kek_pii_v1",
        "audit": "kek_audit_v1",
    }
    
    def get_domain_kek(self, domain: str) -> str:
        kek = self.DOMAIN_KEKS.get(domain)
        if not kek:
            raise ValueError(f"Unknown key domain: {domain}")
        return kek
```

### API Routes: `api/routes/security.py`

```python
router = APIRouter(prefix="/security", tags=["security"])

@router.post("/authorize")
async def authorize(req: AuthorizeRequest, svc=Depends(get_security)):
    return await svc.evaluate_policy(req.to_policy_input())

@router.post("/content/evaluate")
async def evaluate_content(req: ContentEvalRequest, svc=Depends(get_security)):
    return await svc.evaluate_content(req.content, req.source)

@router.post("/tool/validate")
async def validate_tool(req: ToolValidateRequest, svc=Depends(get_security)):
    return await svc.validate_tool_request(req)
```

---

## Part B: Observability Platform

### Objective

Instrument the entire Butler backend with:
- OpenTelemetry traces, metrics, and logs
- Butler-specific semantic conventions (workflow, task, tool spans)
- SLO definitions and error budget alerting
- Health dashboards with Prometheus exposition
- Cardinality control for metric labels

### Core Instrumentation: `core/observability.py`

```python
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_observability(app, service_name: str, otel_endpoint: str | None):
    """Configure full OTel stack with Butler semantic conventions."""
    
    if not otel_endpoint:
        return  # Skip in dev/test without collector
    
    # Traces
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint))
    )
    trace.set_tracer_provider(trace_provider)
    
    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otel_endpoint),
        export_interval_millis=15000,
    )
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    
    # Auto-instrument FastAPI, SQLAlchemy, Redis
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
```

### Butler Metrics: `core/metrics.py`

```python
from opentelemetry import metrics

meter = metrics.get_meter("butler")

# --- Workflow Metrics ---
workflow_started = meter.create_counter(
    "butler.workflow.started_total",
    description="Total workflows started",
)
workflow_completed = meter.create_counter(
    "butler.workflow.completed_total",
    description="Total workflows completed successfully",
)
workflow_failed = meter.create_counter(
    "butler.workflow.failed_total",
    description="Total workflows failed",
)
workflow_duration = meter.create_histogram(
    "butler.workflow.duration_seconds",
    description="Workflow execution duration",
    unit="s",
)

# --- Tool Metrics ---
tool_calls = meter.create_counter(
    "butler.tool.calls_total",
    description="Total tool invocations",
)
tool_duration = meter.create_histogram(
    "butler.tool.duration_seconds",
    description="Tool execution duration",
    unit="s",
)

# --- Intent Metrics ---
intent_classified = meter.create_counter(
    "butler.intent.classified_total",
    description="Total intents classified",
)
intent_duration = meter.create_histogram(
    "butler.intent.classification_duration_seconds",
    description="Intent classification latency",
    unit="s",
)

# --- LLM Metrics ---
llm_tokens = meter.create_counter(
    "butler.llm.tokens_total",
    description="Total LLM tokens consumed",
)

# --- Security Metrics ---
injection_suspected = meter.create_counter(
    "ai_security.prompt_injection_suspected_total",
    description="Suspected prompt injection attempts",
)
tool_blocked = meter.create_counter(
    "ai_security.tool_request_blocked_total",
    description="Tool requests blocked by policy",
)
```

### Tracing Helpers: `core/tracing.py`

```python
from opentelemetry import trace
from functools import wraps

tracer = trace.get_tracer("butler")

def traced(span_name: str, attributes: dict = None):
    """Decorator to trace a function with Butler semantic conventions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("butler.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("butler.status", "error")
                    span.set_attribute("error.class", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator

# Usage example:
# @traced("butler.tool.execute", {"butler.tool.name": "search_web"})
# async def execute_search(query: str): ...
```

---

## Part C: Device, Vision & Audio Services (API Stubs)

These services are hardware-dependent and will initially be implemented as API contract stubs with proper schemas, ready for real provider integration.

### `services/device/service.py` — Device Registry Stub

```python
class DeviceService:
    """Device registry and control plane — stub implementation.
    
    Full implementation requires companion app (Android/iOS) integration.
    Stub provides the API contract and data model.
    """
    
    async def register_device(self, account_id: str, device_info: dict) -> Device:
        device = Device(
            owner_id=uuid.UUID(account_id),
            protocol=device_info.get("protocol", "api"),
            vendor=device_info.get("vendor", "unknown"),
            model=device_info.get("model", "unknown"),
            capabilities=device_info.get("capabilities", []),
            trust_state="pending",
            online_state="offline",
        )
        self._db.add(device)
        await self._db.commit()
        return device
    
    async def list_devices(self, account_id: str) -> list[Device]:
        result = await self._db.execute(
            select(Device).where(Device.owner_id == uuid.UUID(account_id))
        )
        return result.scalars().all()
    
    async def get_state(self, device_id: str) -> dict:
        cached = await self._redis.get(f"device:{device_id}:state")
        if cached:
            return json.loads(cached)
        return {"status": "unknown", "message": "Device state not available"}
    
    async def send_command(self, device_id: str, command: dict) -> dict:
        # Stub — requires real adapter
        return {"status": "queued", "message": "Command queued for device"}
```

### `services/vision/service.py` — Vision Pipeline Stub

```python
class VisionService:
    """Stacked vision perception — stub implementation.
    
    Full implementation requires GPU inference servers (YOLOv8, PaddleOCR, SAM2, Qwen2.5-VL).
    Stub provides the API contract for integration testing.
    """
    
    async def detect(self, image_data: bytes, classes: list[str] = None, threshold: float = 0.5) -> dict:
        return {
            "objects": [],
            "objects_count": 0,
            "model_used": "stub",
            "processing_time_ms": 0,
            "verified": False,
            "message": "Vision service stub — requires GPU inference backend",
        }
    
    async def ocr(self, image_data: bytes, languages: list[str] = None) -> dict:
        return {
            "text": "",
            "blocks": [],
            "model_used": "stub",
            "processing_time_ms": 0,
            "message": "OCR service stub — requires PaddleOCR backend",
        }
    
    async def reason(self, image_data: bytes, context: dict) -> dict:
        return {
            "reasoning": "Vision reasoning stub",
            "model_used": "stub",
            "message": "Requires Qwen2.5-VL inference backend",
        }
```

### `services/audio/service.py` — Audio Pipeline Stub

```python
class AudioService:
    """Stacked audio perception — stub implementation.
    
    Full implementation requires STT models (Whisper, Parakeet) and TTS (Coqui).
    Stub provides the API contract.
    """
    
    async def transcribe(self, audio_data: bytes, language: str = "en", quality: str = "balanced") -> dict:
        return {
            "transcript": "",
            "confidence": 0.0,
            "model_used": "stub",
            "processing_time_ms": 0,
            "message": "STT service stub — requires Whisper/Parakeet backend",
        }
    
    async def synthesize(self, text: str, voice_id: str = None) -> dict:
        return {
            "audio_data": "",
            "duration_ms": 0,
            "message": "TTS service stub — requires Coqui TTS backend",
        }
    
    async def identify_music(self, audio_data: bytes) -> dict:
        return {
            "title": None,
            "artist": None,
            "score": 0.0,
            "message": "Music ID stub — requires Chromaprint + AcoustID",
        }
```

### API Routes for Device/Vision/Audio

```python
# api/routes/device.py
router = APIRouter(prefix="/devices", tags=["device"])

@router.get("/")
async def list_devices(account=Depends(get_current_account), svc=Depends(get_device)):
    return await svc.list_devices(account.account_id)

@router.post("/register")
async def register_device(req: RegisterDeviceRequest, account=Depends(get_current_account), svc=Depends(get_device)):
    return await svc.register_device(account.account_id, req.dict())

@router.get("/{device_id}/state")
async def get_device_state(device_id: str, svc=Depends(get_device)):
    return await svc.get_state(device_id)

@router.post("/{device_id}/commands")
async def send_command(device_id: str, req: DeviceCommandRequest, svc=Depends(get_device)):
    return await svc.send_command(device_id, req.dict())

# api/routes/vision.py
router = APIRouter(prefix="/vision", tags=["vision"])

@router.post("/detect")
async def detect(req: DetectRequest, svc=Depends(get_vision)):
    return await svc.detect(req.image_data, req.classes, req.threshold)

@router.post("/ocr")
async def ocr(req: OCRRequest, svc=Depends(get_vision)):
    return await svc.ocr(req.image_data, req.languages)

@router.post("/reason")
async def reason(req: ReasonRequest, svc=Depends(get_vision)):
    return await svc.reason(req.image_data, req.context)

# api/routes/audio.py
router = APIRouter(prefix="/audio", tags=["audio"])

@router.post("/stt")
async def transcribe(req: STTRequest, svc=Depends(get_audio)):
    return await svc.transcribe(req.audio_data, req.language, req.quality_mode)

@router.post("/tts")
async def synthesize(req: TTSRequest, svc=Depends(get_audio)):
    return await svc.synthesize(req.text, req.voice_id)

@router.post("/music/identify")
async def identify_music(req: MusicIDRequest, svc=Depends(get_audio)):
    return await svc.identify_music(req.audio_data)
```

---

## Dependencies to Add

```toml
opentelemetry-api = ">=1.24"
opentelemetry-sdk = ">=1.24"
opentelemetry-exporter-otlp-proto-grpc = ">=1.24"
opentelemetry-instrumentation-fastapi = ">=0.45b"
opentelemetry-instrumentation-sqlalchemy = ">=0.45b"
opentelemetry-instrumentation-redis = ">=0.45b"
cryptography = ">=42.0"       # AES-GCM, key management
```

---

## Final `main.py` Assembly (All Phases)

```python
"""Butler API — complete service assembly."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import settings
from infrastructure.database import init_db, close_db
from infrastructure.cache import redis_client
from core.middleware import RequestContextMiddleware
from core.errors import problem_exception_handler, Problem
from core.logging import setup_logging
from core.observability import setup_observability

# All route imports
from api.routes.auth import router as auth_router
from api.routes.gateway import router as gateway_router
from api.routes.orchestrator import router as orchestrator_router
from api.routes.memory import router as memory_router
from api.routes.tools import router as tools_router
from api.routes.search import router as search_router
from api.routes.ml import router as ml_router
from api.routes.realtime import router as realtime_router
from api.routes.communication import router as communication_router
from api.routes.security import router as security_router
from api.routes.device import router as device_router
from api.routes.vision import router as vision_router
from api.routes.audio import router as audio_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.SERVICE_NAME, settings.ENVIRONMENT)
    await init_db()
    await redis_client.connect()
    yield
    await redis_client.disconnect()
    await close_db()

app = FastAPI(title="Butler API", version=settings.SERVICE_VERSION, lifespan=lifespan)

# Middleware
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Observability
setup_observability(app, settings.SERVICE_NAME, settings.OTEL_ENDPOINT)

# Error handler
app.add_exception_handler(Problem, problem_exception_handler)

# Routes (Phase 0-6)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(gateway_router, prefix="/api/v1")
app.include_router(orchestrator_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(ml_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/api/v1")
app.include_router(communication_router, prefix="/api/v1")
app.include_router(security_router, prefix="/api/v1")
app.include_router(device_router, prefix="/api/v1")
app.include_router(vision_router, prefix="/api/v1")
app.include_router(audio_router, prefix="/api/v1")
```

---

## Verification Checklist

### Security
- [ ] Trust classifier assigns correct levels per source type
- [ ] Channel separator never routes untrusted to instructions
- [ ] Injection detection flags suspicious patterns
- [ ] Policy decision point blocks unauthed device control
- [ ] Tool capability gate enforces approval when required
- [ ] Memory isolation enforces assurance level minimums
- [ ] AES-256-GCM encrypt/decrypt roundtrip works

### Observability
- [ ] OTel traces captured for all service calls
- [ ] Custom Butler metrics (workflow, tool, intent) record
- [ ] Prometheus `/metrics` endpoint exposes all counters/histograms
- [ ] Health endpoints respond with dependency status
- [ ] Cardinality control prevents high-cardinality labels

### Device/Vision/Audio
- [ ] Device registration creates record in DB
- [ ] Device state reads from Redis cache
- [ ] Vision/Audio stubs return proper contract shapes
- [ ] All error codes follow RFC 9457

---

## Final Docker Compose (All Services)

```yaml
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://butler:butler@db:5432/butler
      REDIS_URL: redis://cache:6379/0
      ENVIRONMENT: development
      OTEL_ENDPOINT: http://otel-collector:4317
    depends_on: [db, cache]
  
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: butler
      POSTGRES_USER: butler
      POSTGRES_PASSWORD: butler
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  
  cache:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.96.0
    ports: ["4317:4317", "4318:4318", "8889:8889"]
    volumes: ["./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml"]

volumes:
  pgdata:
```

---

*Phase 6 complete → All 16 services implemented → Butler backend is production-grade.*
