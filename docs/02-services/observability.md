# Observability Platform - Technical Specification

> **For:** Engineering, DevOps  
> **Status:** Partial-Active (v3.1) — OTEL export configured; dashboards and SLO alerting need deployment validation
> **Version:** 3.1  
> **Reference:** Butler telemetry platform with workflow/agent observability and SLOs  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **Collector Pipeline** | ✅ IMPLEMENTED | OTel Collector with OTLP/gRPC — configured via docker-compose |
| 2 | **Semantic Schema** | ✅ IMPLEMENTED | Butler-standard span attributes + structlog JSON backend |
| 3 | **Backends** | ⚪ PARTIAL | Mimir/Tempo/Loki config defined; not validated in prod |
| 4 | **Dashboards** | ⚪ PARTIAL | Grafana layout defined; needs deployment + datasource wiring |
| 5 | **SLO Engine** | ⚪ PARTIAL | Prometheus SLO rules in `docker-compose`; not monitored live |
| 6 | **Profiling** | 🔲 STUB | Pyroscope integration — not configured |

---

## 0.1 v3.1 Notes

> **Current state as of 2026-04-19**

### What is working
- **Structured logging**: all services use `structlog` with JSON format; log lines include `account_id`, `request_id`, `event`, `duration_ms`
- **OTEL tracing**: `opentelemetry-sdk` is installed; `configure_telemetry()` in `core/telemetry.py` sets up OTLP gRPC export
- **OTel Collector**: `docker-compose.yml` runs `otel/opentelemetry-collector-contrib` receiving on port `4317`

### What needs deployment validation
- **Mimir** (metrics): OTLP remote-write configured; needs a running Mimir instance
- **Tempo** (traces): OTLP export configured; needs a running Tempo instance
- **Loki** (logs): Grafana Alloy log pipeline config present; needs wiring to Loki
- **Grafana**: Docker Compose service defined; dashboards in `observability/grafana/` need provisioning

### What is NOT yet implemented
- **Pyroscope** continuous profiling: no integration code exists yet
- **SLO burn-rate alerts**: Prometheus rules are specified in the doc but not in the repo's `alerts.yml`
- **Butler-specific agent observability**: span attributes for `tool_name`, `model_tier`, `memory_tier` not yet emitted by all services

### Key Files
| File | Role |
|------|------|
| `core/telemetry.py` | `configure_telemetry()` — OTel SDK setup |
| `core/middleware.py` | Request tracing middleware (span creation) |
| `docker-compose.yml` | OTel Collector + Grafana + Tempo config stanzas |
| `observability/` | Grafana dashboard definitions (if present) |

---

## 1. Platform Overview

### 1.1 Purpose
The Observability Platform provides **telemetry collection, processing, correlation, reliability measurement, and incident signal routing** across Butler services, workflows, tools, and agent runtime.

This is NOT a service that exports metrics. It's a **platform** with:
- OTel Collector pipeline architecture
- Storage backends for metrics, traces, logs, profiles
- Dashboards, SLOs, alert routing
- Schema and retention governance

### 1.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Butler Observability Platform                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  SERVICES                                                                 │
│  ├── Gateway, Auth, Orchestrator, Memory, ML, Tools, etc.              │
│       │                                                                   │
│       ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ OpenTelemetry SDKs (instrumentation)                   │   │
│  │  • Metrics                                          │   │
│  │  • Traces                                          │   │
│  │  • Logs                                           │   │
│  │  • Profiles                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│       │                                                                   │
│       ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ OTel Collector Pipeline                                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐      │   │
│  │  │  metrics   │  │  traces   │  │   logs    │      │   │
│  │  │ pipeline   │  │ pipeline  │  │ pipeline  │      │   │
│  │  └────────────┘  └────────────┘  └────────────┘      │   │
│  │        │              │              │                   │   │
│  │        ▼              ▼              ▼                   │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │     profile ingestion (optional)            │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│       │                                                                   │
│       ▼                                                                   │
│  BACKENDS                                                                 │
│  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐                │
│  │ Prometheus│  │  Tempo  │  │  Loki   │  │Pyroscope │                │
│  │ / Mimir  │  │ traces  │  │  logs   │  │profiles  │                │
│  └──────────┘  └─────────┘  └─────────┘  └──────────┘                │
│       │           │          │            │                               │
│       └───────────┴──────────┴────────────┴───────────────┘              │
│                         │                                              │
│                         ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ GRAFANA + SLOs + ALERT ROUTING                                  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Boundaries

| Component | Boundary |
|-----------|----------|
| Services | Only instrument - never configure backends |
| Collector | Receives, processes, exports telemetry |
| Backends | Prometheus/Mimir, Tempo, Loki, Pyroscope |
| Grafana | Visualization and SLO dashboards |

**NOT** a service that does application logic.

---

## 2. Telemetry Schema Governance

### 2.1 Butler Semantic Conventions

```python
BUTLER_SCHEMA = {
    "resource_attributes": {
        "service.name": "required",           # butler.gateway, butler.orchestrator
        "service.version": "required",       # e.g., v2.0.0
        "deployment.environment": "required", # dev, staging, prod
        "butler.account_id": "required",   # Multi-tenant isolation
        "butler.service_region": "optional", # e.g., us-east-1
    },
    
    "span_attributes": {
        # Workflow
        "butler.workflow_id": "required",
        "butler.workflow_name": "required",
        "butler.workflow_status": "required", # started, completed, failed
        
        # Task
        "butler.task_id": "optional",
        "butler.task_type": "optional",  # planning, execution, approval
        
        # Session
        "butler.session_id": "required",
        "butler.channel": "optional",  # mobile, web, voice
        
        # Intent/Tool
        "butler.intent": "optional",
        "butler.tool_name": "optional",
        
        # Errors
        "error.class": "if_error",
        "error.message": "if_error",
    },
    
    "metric_attributes": {
        # Use ONLY for SLOs and billing
        "butler.service_name": "required",
        "butler.workflow_name": "optional",
        "butler.channel": "optional",
    }
}
```

### 2.2 Cardinality Control Policy

**CRITICAL RULE - Never put in labels:**

```python
# FORBIDDEN - these destroy performance and cost
HIGH_CARDINALITY_LABELS = [
    "user_id",           # Use trace_id or span attributes
    "session_id",        # Use span attributes
    "task_id",           # Use span attributes
    "trace_id",         # Use trace context
    "request_id",       # Use log fields
    "email",            # Use log fields
    "ip_address",       # Security log only
    "device_token",    # Push only
    "conversation_id", # Use span attributes
]

# ALLOWED - bounded cardinality
SAFE_LABELS = [
    "service.name",           # 16 services
    "deployment.environment", # 3 envs
    "channel",                # 4 channels
    "status",                 # limited set
    "error_class",           # 20-30 error types
    "method",               # HTTP verbs
    "tool_name",             # ~50 tools
    "intent",               # ~30 intents
]
```

**Implementation:**

```python
# In Collector processors
processors:
  # Drop high-cardinality attributes from metrics
  - transform:
      # Convert high-cardinality to log fields instead
      rum_attribute: |
        NewMetric(attributes["butler.workflow_id"]) 
        >> LogField("workflow_id")
```

---

## 3. OTel Collector Pipeline

### 3.1 Collector Configuration

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
  
  prometheus:
    config:
      scrape_configs:
        - job_name: 'butler-services'
          scrape_interval: 15s

processors:
  # Batch processing
  batch:
    timeout: 5s
    send_batch_size: 1000
  
  # Resource attributes
  resource:
    attributes:
      - key: deployment.environment
        from_attribute: DEPLOYMENT_ENV
  
  # Cardinality control
  datadog:
    hostname_prefix: "butler-"
    tags_env: DEPLOYMENT_ENV
  
  # Memory control
  mem_limiter:
    check_interval: 1s
    limit_mib: 1000

exporters:
  # Metrics → Prometheus/Mimir
  prometheus:
    endpoint: 0.0.0.0:8889
    namespace: butler
  
  # Traces → Tempo
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
  
  # Logs → Loki
  loki:
    endpoint: loki:3100
    labels:
      service: "butler"
  
  # Profiles → Pyroscope (optional)
  pyroscope:
    endpoint: pyroscope:4317

service:
  pipelines:
    metrics:
      receivers: [otlp, prometheus]
      processors: [batch, resource, mem_limiter]
      exporters: [prometheus]
    
    traces:
      receivers: [otlp]
      processors: [batch, resource, mem_limiter]
      exporters: [otlp/tempo]
    
    logs:
      receivers: [otlp]
      processors: [batch, resource, mem_limiter]
      exporters: [loki]
```

### 3.2 Service Configuration

```python
# Each service uses OTel SDK
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Initialize
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="otel-collector:4317"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

meter = MeterProvider(
    exporter=OTLPMetricExporter(endpoint="otel-collector:4317")
)
```

---

## 4. Butler Workflow Observability

### 4.1 Workflow Span Types

```python
class ButlerWorkflowSpans:
    """AI-agent observability spans"""
    
    # Intent classification
    with tracer.start_as_current_span("butler.intent.classify") as span:
        span.set_attribute("butler.intent.input", user_input[:100])
        span.set_attribute("butler.intent.classified", intent)
        span.set_attribute("butler.intent.confidence", confidence)
    
    # Context retrieval
    with tracer.start_as_current_span("butler.context.retrieve") as span:
        span.set_attribute("butler.context.query", query)
        span.set_attribute("butler.context.results", len(results))
        span.set_attribute("butler.context.latency_ms", latency_ms)
    
    # Plan creation
    with tracer.start_as_current_span("butler.plan.create") as span:
        span.set_attribute("butler.plan.steps", len(plan.steps))
        span.set_attribute("butler.plan.tool_count", len(plan.tools))
    
    # Tool execution
    with tracer.start_as_current_span("butler.tool.execute") as span:
        span.set_attribute("butler.tool.name", tool_name)
        span.set_attribute("butler.tool.input_tokens", input_tokens)
        span.set_attribute("butler.tool.output_tokens", output_tokens)
        span.set_attribute("butler.tool.duration_ms", duration_ms)
    
    # Approval wait
    with tracer.start_as_current_span("butler.approval.wait") as span:
        span.set_attribute("butler.approval.type", approval_type)
        span.set_attribute("butler.approval.duration_ms", wait_ms)
    
    # Compensation
    with tracer.start_as_current_span("butler.compensation.execute") as span:
        span.set_attribute("butler.compensation.trigger", trigger)
        span.set_attribute("butler.compensation.recovered", recovered)
```

### 4.2 Butler Metrics

```yaml
butler_metrics:
  # Workflow
  butler.workflow.started_total:
    type: counter
    description: Total workflows started
  
  butler.workflow.completed_total:
    type: counter  
    description: Total workflows completed successfully
  
  butler.workflow.failed_total:
    type: counter
    description: Total workflows failed
  
  butler.workflow.duration_seconds:
    type: histogram
    description: Workflow execution duration
    buckets: [1, 5, 10, 30, 60, 300, 600]
  
  # Approval
  butler.approval.requested_total:
    type: counter
    
  butler.approval.wait_duration_seconds:
    type: histogram
    description: Approval wait time
  
  butler.approval.denied_total:
    type: counter
  
  # Tools
  butler.tool.calls_total:
    type: counter
    labels: [tool_name, status]
  
  butler.tool.duration_seconds:
    type: histogram
    labels: [tool_name]
  
  # LLM/ML
  butler.llm.tokens_total:
    type: counter
    labels: [model, task]
  
  butler.llm.cost_estimate_total:
    type: counter
    labels: [model]
  
  # Intent
  butler.intent.classification_duration_seconds:
    type: histogram
  
  butler.intent.classified_total:
    type: counter
    labels: [intent]
  
  # Context
  butler.context.retrieval_duration_seconds:
    type: histogram
  
  butler.context.results_total:
    type: histogram
```

### 4.3 Exemplars

```python
# Connect latency spikes to traces
histogram = butler.workflow.duration_seconds
histogram.exemplar = {
    "trace_id": workflow_trace_id,
    "span_id": workflow_span_id,
    "timestamp": now()
}
```

---

## 5. SLO and Error Budget

### 5.1 Butler SLOs

```yaml
slos:
  # Availability
  butler_availability:
    target: 0.998  # 99.8%
    measurement: 5m
    error_budget: 14.4m/day  # ~1.4% of 24h
  
  butler_api_availability:
    target: 0.999
    measurement: 5m
  
  # Latency
  butler_workflow_latency_p50:
    target: 0.95  # P50 < 10s
    measurement: 5m
  
  butler_workflow_latency_p99:
    target: 0.90  # P99 < 60s
    measurement: 5m
  
  butler_tool_latency_p99:
    target: 0.95  # P99 < 5s
    measurement: 5m
  
  # Workflow completion
  butler_workflow_completion:
    target: 0.95
    measurement: 1h
  
  # Approval delivery
  butler_approval_delivery:
    target: 0.99
    measurement: 5m
```

### 5.2 Error Budget Alerts

```yaml
alerts:
  - name: AvailabilityErrorBudgetBurn
    expr: |
      sum(rate(butler_availability_error_total[1h])) 
      / sum(rate(butler_availability_total[1h])) 
      > 0.001  # 0.1% of budget burned in 1h
    severity: warning
  
  - name: LatencyBudgetThreat
    expr: |
      histogram_quantile(0.99, rate(butler_workflow_duration_seconds_bucket[5m])) 
      > 60
    severity: warning
  
  - name: HighFailureRate
    expr: |
      sum(rate(butler_workflow_failed_total[5m])) 
      / sum(rate(butler_workflow_started_total[5m])) 
      > 0.05
    severity: critical
```

---

## 6. Cross-Signal Correlation

### 6.1 Trace-Log-Metric Linking

```python
# In logs - always include trace_id
logger.info(
    "tool_execution_completed",
    butler_workflow_id=workflow_id,  # Required
    trace_id=trace_id,               # For correlation
    butler_tool_name=tool_name,
    duration_ms=duration_ms,
    status="success"
)

# In traces
span.set_attribute("trace_id", trace_id)
span.add_event("log", attributes={"log_id": log_id})

# In metrics - use exemplars
histogram.record(value, exemplar={
    "trace_id": trace_id,
    "span_id": span_id
})
```

### 6.2 Service Graphs

```python
# Auto-generate from traces via Tempo
# Link services: gateway → orchestrator → memory → tools
```

---

## 7. Continuous Profiling (Optional)

### 7.1 Profile Collection

```yaml
# Enable in Orchestrator, Memory, Vision, ML
profilers:
  cpu:
    enabled: true
    interval: 10s
  
  memory:
    enabled: true
    interval: 30s
  
pyroscope:
  targets:
    - butler_orchestrator
    - butler_memory
    - butler_ml_inference
```

### 7.2 Use Cases

- Find hot code paths in workflows
- Memory leak detection
- GPU utilization analysis (ML)

---

## 8. Health Endpoints

### 8.1 Multi-Level Health

```yaml
GET /health/live
  # Simple alive check - no dependencies
  Response: { "alive": true }

GET /health/startup  
  # Dependency check for startup
  Response: { "ready": true, "missing_deps": [] }

GET /health/ready
  # Full readiness - DB, Redis, external services
  Response: 
    ready: true
    checks:
      database: healthy
      redis: healthy
      otel_collector: healthy

GET /health/degraded
  # Running but degraded - reduced features
  Response:
    degraded: true
    reason: "redis_pool_exhausted"
    workarounds: ["using_local_cache"]

GET /health/deps
  # Individual dependency status
  Response:
    dependencies:
      database: { status: up, latency_ms: 5 }
      redis: { status: up, latency_ms: 2 }
      otel_collector: { status: up, latency_ms: 10 }
```

---

## 9. Retention and Sampling

### 9.1 Retention Policy

```yaml
retention:
  metrics:
    raw: 15d
    aggregated: 90d
  
  traces:
    error: 30d          # Keep all errors
    audit: 1y          # Security logs
    standard: 7d
    sampling: 1d
  
  logs:
    error/debug: 30d
    audit/security: 1y
    standard: 7d
    session: 1d
  
  profiles:
    retention: 7d
```

### 9.2 Sampling Policy

```yaml
sampling:
  traces:
    # Always capture errors
    error: 1.0  # 100%
    
    # Rare/slow workflows - 100%
    butler_approval_wait: 1.0
    
    # High-volume - 10%
    standard: 0.1
    
    # Health checks - 1%
    health_check: 0.01
  
  logs:
    error: 1.0
    warning: 0.5
    info: 0.1
```

---

## 10. Observability Dashboard

### 10.1 Key Grafana Panels

```yaml
dashboards:
  Butler Overview:
    - Workflow completion rate (SLO)
    - Workflow latency (P50/P95/P99)
    - Error budget remaining
    - Active sessions
  
  Service Health:
    - Request rate per service
    - Error rate per service  
    - Latency per service
    - K6 availability per service
  
  Workflow Analysis:
    - Workflow timeline (Trace view)
    - Intent distribution
    - Tool execution latency
    - Approval wait times
  
  System:
    - CPU/Memory per pod
    - Database connections
    - Redis pool usage
    - OTel Collector queue
```

---

## 11. Alert Routing

### 11.1 Severity Matrix

| Alert Type | Severity | Channels | Runbook |
|-----------|----------|----------|---------|
| SLO breach | critical | PagerDuty, SMS, Slack | /runbooks/slo-breach |
| Workflow failed | high | Slack | /runbooks/workflow-fail |
| Tool timeout | medium | Slack | /runbook/tool-timeout |
| High latency | medium | Slack | /runbook/latency |
| Service down | critical | PagerDuty, SMS | /runbook/service-down |
| DB connection pool | high | PagerDuty, Slack | /runbook/db-pool |
| Memory leak | high | PagerDuty | /runbook/memory |

---

## 12. Runbooks Quick Reference

### 12.1 High Error Rate

```bash
# Check services
curl http://grafana:3000/api/datasources/1/query...

# Get top errors
kubectl logs -l app=orchestrator | grep ERROR | head -50

# Check traces
curl http://tempo:3100/api/search?service=orchestrator&limit=10
```

### 12.2 High Latency

```bash
# Find slow requests
curl http://grafana:3000/api/v1/query?query=histogram_quantile...

# Check traces
curl http://tempo:3100/api/search?latency>10s&limit=20
```

### 12.3 Workflow Stall

```bash
# Find stuck workflows
kubectl logs -f butler-orchestrator | grep "task_timeout"

# Trace workflow
curl http://tempo:3100/api/traces/{workflow_trace_id}
```

---

## 13. API Contracts

### 13.1 Metrics

```yaml
GET /metrics
  Response: Prometheus format

GET /metrics/summary
  Response:
    {
      "requests_total": 1000000,
      "error_rate": 0.01,
      "p99_latency": 500,
      "slo_status": "healthy"
    }
```

### 13.2 Traces

```yaml
GET /api/v1/traces/{trace_id}
  # Returns full trace with spans
  Response:
    {
      "trace_id": "...",
      "duration_ms": 5240,
      "spans": [...],
      "services": ["gateway", "orchestrator", "tools"]
    }

GET /api/v1/traces/search
  # Search traces
  Query: service, duration, attributes
```

### 13.3 SLO Status

```yaml
GET /api/v1/slo/status
  Response:
    {
      "availability": { "current": 0.998, "target": 0.998, "remaining": "14.3m" },
      "latency_p50": { "current": "8s", "target": "10s" },
      "latency_p99": { "current": "45s", "target": "60s" }
    }
```

---

*Document owner: Observability Team*  
*Version: 2.0 (Implementation-ready)*  
*Last updated: 2026-04-18*