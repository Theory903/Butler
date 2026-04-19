# Butler Full Services Strategic Reference

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide a future multi-agent execution system with explicit, service-by-service guidance for building Butler's complete service architecture, using Hermes as an MIT-licensed reference where applicable and designing Butler-native pieces where needed.

**Architecture:** Modular monolith first with strict service boundaries preserved for future extraction into separate services. Each service follows KISS and SOLID principles with clear interfaces, explicit dependencies, and production-hardening considerations.

**Tech Stack:** Python/FastAPI core, PostgreSQL primary DB, Redis cache/session store, Docker containerization, JWT auth, structured logging with correlation IDs.

---

## Understanding Summary

- What is being built: Complete Butler personal AI system with all 17 services
- Why it exists: To create a production-grade JARVIS-class assistant runtime that can grow from MVP to full platform
- Who it is for: Future multi-agent execution system that will implement this plan
- Key constraints: 
  - Must preserve clean seams for future service extraction
  - Must maintain backward compatibility within MVP golden path
  - Must use Hermes as reference where it has solid implementations
  - Must design Butler-native pieces where Hermes doesn't cover requirements
  - Must optimize for execution order, architecture map, and production hardening simultaneously
- Explicit non-goals: 
  - Do not build all services in parallel without sequencing
  - Do not ignore service boundaries and create spaghetti dependencies
  - Do not sacrifice observability and failure handling for demo features
  - Do not hardcode secrets or use insecure defaults in any service

## Assumptions

- Butler docs (BRD, PRD, TRD, HLD, LLD, service specs) are source of truth
- Hermes Agent is an MIT-licensed reference project safe to copy from where implementations are solid
- Each service can be understood and implemented in isolation with clear interface contracts
- Production hardening (security, observability, resilience) must be baked in from the start
- Service dependencies should be explicit and injectable, not hardcoded or imported
- The modular monolith approach preserves extraction boundaries for future microservices
- All services must be testable in isolation with mocked dependencies
- Runtime behavior must be observable and diagnosable without source inspection

## Open Questions

- None - understanding lock confirmed

---

## Decision Log

| Decision | Alternatives Considered | Why This Option |
|----------|------------------------|-----------------|
| Use Hermes as reference implementation source | Build everything from scratch, ignore existing work | Hermes provides battle-tested patterns for config, logging, tool gateways, memory management that save significant implementation time |
| Default to adapted copy for Hermes-backed areas | Direct copy or reference-only | Direct copy risks importing Hermes-specific assumptions; reference-only loses implementation guidance; adapted copy gives best balance |
| Separate strategic reference document | Fold into MVP planning draft | Keeps MVP plan focused on 2-day execution while providing comprehensive long-term reference |
| Very explicit detail level for multi-agent execution | Moderate or high-level only | Future execution system needs service-by-service guidance, dependencies, sequencing, and verification expectations |
| Optimize for all three dimensions simultaneously | Focus on just one dimension | Execution order, architecture, and hardening are interdependent; optimizing one without the others creates fragility |

---

## Strategic Reference: Service-by-Service Guidance

### 1. Gateway Service (8000)

**Purpose:** External API contract boundary, auth validation, request normalization, forwarding semantics only.

**Hermes Reference Areas:**
- **Direct copy patterns:** `hermes_cli/config.py` for canonical config loading, file permission handling, UTF-8 enforcement
- **Adapted copy:** `hermes_logging.py` for idempotent centralized logging with correlation/request IDs
- **Reference only:** `hermes_cli/gateway.py` for CLI-specific gateway concepts (adapt to HTTP API context)

**Butler-Native Implementation:**
- Thin API routes that validate JWT and forward to orchestrator
- No business logic in route handlers
- Explicit dependency injection for auth service
- Request/response normalization layer
- Health endpoint with startup failure reason surfacing

**Dependencies:**
- Auth service (for JWT validation)
- Orchestrator service (for request forwarding)
- Config service (centralized settings)
- Logging service (correlation IDs)

**Execution Order:** Build after Auth service contract is stable

**Production Hardening:**
- Never persist resolved secrets back to config
- Fail startup loudly with exact reason
- Include correlation IDs in all logs
- Rate limiting and input validation
- Graceful degradation when dependencies unavailable

**Verification Expectations:**
- `/health` returns actionable failure reason when unhealthy
- Invalid token returns 401 with clear message
- Request correlation ID appears in logs and responses
- No hardcoded secrets in MVP auth path

### 2. Auth Service (8001)

**Purpose:** User login, token issuing, session tracking, password security.

**Hermes Reference Areas:**
- **Direct copy patterns:** `tests/hermes_cli/test_config_env_expansion.py` for env var expansion behavior and unresolved-placeholder preservation
- **Adapted copy:** `hermes_cli/config.py` for raw-vs-resolved config separation (keep raw placeholders separate from resolved runtime settings)
- **Reference only:** `hermes_cli/auth.py` for provider credential resolution concepts (adapt to email/password flow)

**Butler-Native Implementation:**
- PostgreSQL-backed user storage with Argon2id password hashing
- JWT token issuance with user_id and email claims
- Token validation reusable by Gateway/Orchestrator/Memory
- No in-memory auth persistence for golden path
- Secret handling that never writes resolved secrets to disk

**Dependencies:**
- Config service (database connection strings)
- Logging service (audit login attempts)
- Security service (crypto helpers)

**Execution Order:** Build first - foundation for all authenticated services

**Production Hardening:**
- Argon2id for password hashing (not fake crypto)
- JWT with proper claims, expiry, and validation
- Centralized secret/config loading
- Input validation everywhere
- No hardcoded secrets in service modules
- No fake encryption in security service

**Verification Expectations:**
- Valid email/password returns token + user_id
- Invalid credentials return 401
- Token can be consumed by chat and history routes
- Auth/config path never persists resolved secrets or hardcoded credentials

### 3. Orchestrator Service (8002)

**Purpose:** Own classify → build context → generate response flow, use Memory and Tools via clean interfaces.

**Hermes Reference Areas:**
- **Direct copy patterns:** `agent/memory_manager.py` for non-fatal provider orchestration and defensive separation between recall and sync paths
- **Adapted copy:** `tools/managed_tool_gateway.py` for explicit gateway/token resolution seams and token freshness checks
- **Reference only:** `model_tools.py` for tool schema collection concepts (adapt to tool interface)

**Butler-Native Implementation:**
- Intent classification (simple keyword matching for MVP)
- Context building from Memory service
- Response generation using simple templates
- Tool orchestration via Tools service interface
- Message persistence through Memory service for golden flow
- Ordered per-session processing (no single-slot pending message overwrite)

**Dependencies:**
- Memory service (for session history)
- Tools service (for tool execution)
- Logging service (debug intent classification)
- Config service (feature flags)

**Execution Order:** Build after Auth and Memory service contracts are stable

**Production Hardening:**
- Preserve ordered per-session processing semantics
- Never use a single mutable pending-message slot
- Fail tool execution explicitly (no silent downgrade to fake success)
- Non-fatal subsystem failures (one tool down doesn't kill orchestrator)
- Clear intent classification logging

**Verification Expectations:**
- Greeting path returns expected greeting
- Tool path uses tools service
- Messages are persisted through memory for golden flow
- Orchestration path preserves message order and does not silently drop or overwrite prior pending work

### 4. Memory Service (8003)

**Purpose:** Stable session history persistence, ordered message storage and retrieval.

**Hermes Reference Areas:**
- **Direct copy patterns:** `tests/gateway/test_flush_memory_stale_guard.py` for stale-overwrite prevention mindset and explicit memory safety checks
- **Adapted copy:** `agent/memory_manager.py` for provider orchestration and non-fatal provider isolation (adapt to service seams)
- **Reference only:** `tools/memory_tool.py` for memory tool interface concepts (adapt to service API)

**Butler-Native Implementation:**
- SQLite-backed persistence (simple for MVP, preserves extraction boundary)
- Session history stored as ordered list of messages
- Append-only persistence for golden path chat transcript
- User and assistant messages saved with role/content/timestamp
- Same session_id survives across request sequence
- Missing/empty history handled cleanly

**Dependencies:**
- Config service (database connection string)
- Logging service (audit memory operations)

**Execution Order:** Build after Auth service contract is stable

**Production Hardening:**
- Memory persistence path is append-ordered and does not overwrite previously persisted golden-path messages
- Guard against stale overwrite patterns
- No fake/no-op storage in production-grade alpha path
- Database connection failures handled explicitly
- Query timeouts and retry logic

**Verification Expectations:**
- Session history returns ordered messages
- Same session_id survives across request sequence within alpha runtime
- Missing/empty history is handled cleanly
- Memory persistence path does not overwrite previously persisted messages

### 5. Tools Service (8005)

**Purpose:** Starter tool registry and execution interface for MVP: send_message, get_time, search_web.

**Hermes Reference Areas:**
- **Direct copy patterns:** `tools/managed_tool_gateway.py` for explicit gateway/token resolution seams and token freshness checks
- **Adapted copy:** `tests/tools/test_managed_tool_gateway.py` for focused env override/gateway resolution tests
- **Reference only:** `tools/registry.py` for tool registration/dispatch concepts (adapt to service interface)

**Butler-Native Implementation:**
- Tool registry that lists and executes starter tools
- At least one real tool executes successfully (get_time)
- Nonexistent tool returns deterministic error
- Tool config resolution explicit and testable
- No hidden errors behind generic success payloads
- No broad external integrations in MVP

**Dependencies:**
- Config service (API keys, external service URLs)
- Logging service (tool execution audit)
- Security service (secret handling for external tools)

**Execution Order:** Build after Auth service contract is stable

**Production Hardening:**
- Tool execution/config resolution failures are explicit and never silently downgraded to fake success
- Environment/token/runtime drift is easy to diagnose
- No tool execution without proper validation
- External tool failures don't crash the service
- Tool registry can be extended without breaking changes

**Verification Expectations:**
- Tools list endpoint returns expected starter tools
- At least one tool executes successfully
- Nonexistent tool returns deterministic error
- Tool execution/config resolution failures are explicit

### 6. Realtime Service (8004) - Post-MVP

**Purpose:** WebSocket connections for real-time bidirectional communication.

**Hermes Reference Areas:**
- **Reference only:** Hermes gateway WebSocket concepts (adapt to Butler service interface)

**Butler-Native Implementation:**
- WebSocket endpoint for real-time client communication
- Connection lifecycle management
- Message broadcasting to subscribed clients
- Authentication via JWT token in connection headers
- Fallback to polling for clients that don't support WebSocket

**Dependencies:**
- Auth service (for JWT validation)
- Orchestrator service (for message processing)
- Memory service (for session history)
- Config service (WebSocket configuration)

**Execution Order:** Build after MVP golden path is stable

**Production Hardening:**
- Connection heartbeat and timeout handling
- Graceful degradation when WebSocket unavailable
- Message queuing for disconnected clients
- Resource limits per connection
- Input validation and sanitization

### 7. ML Service (8006) - Post-MVP

**Purpose:** Machine learning embeddings, recommendations, and model serving.

**Hermes Reference Areas:**
- **Reference only:** Hermes model metadata and tool concepts (adapt to ML service context)

**Butler-Native Implementation:**
- Embedding generation for semantic search
- Model serving for recommendations and classification
- Feature extraction from user interactions
- A/B testing framework for model iterations
- Model versioning and rollback capabilities

**Dependencies:**
- Memory service (for training data)
- Orchestrator service (for feature context)
- Tools service (for data collection tools)
- Config service (model configuration, API keys)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Model loading and inference timeouts
- Graceful degradation when models unavailable
- Resource limits and GPU memory management
- Model drift detection and retraining triggers
- Input validation for model features

### 8. Search Service (8007) - Post-MVP

**Purpose:** Web search, document retrieval, and information extraction.

**Hermes Reference Areas:**
- **Reference only:** Hermes web_tool.py and browser_tool.py concepts (adapt to service interface)

**Butler-Native Implementation:**
- Search API for external information retrieval
- Result ranking and relevance scoring
- Content extraction and summarization
- Caching layer for frequent queries
- Safe search and content filtering

**Dependencies:**
- Tools service (for search execution)
- Memory service (for search history)
- Config service (API keys, search engine configuration)
- Orchestrator service (for search context)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Rate limiting and API key rotation
- Result sanitization and XSS prevention
- Timeout handling for external requests
- Fallback to cached results when external services unavailable
- Content safety filtering

### 9. Communication Service (8008) - Post-MVP

**Purpose:** External messaging platforms (email, SMS, push notifications).

**Hermes Reference Areas:**
- **Reference only:** Hermes notification and messaging tool concepts (adapt to service interface)

**Butler-Native Implementation:**
- Message templating and personalization
- Delivery tracking and receipt confirmation
- Rate limiting and throttling per platform
- Template management and A/B testing
- Opt-in/out preference management

**Dependencies:**
- Auth service (for user identification)
- Memory service (for preference storage)
- Tools service (for external API execution)
- Config service (platform credentials, API keys)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Credential rotation and secure storage
- Delivery failure handling and retry logic
- Spam complaint processing and unsubscribe handling
- Platform-specific compliance (TCPA, CAN-SPAM, GDPR)
- Message queueing for rate limit handling

### 10. Workflows Service (8009) - Post-MVP

**Purpose:** Workflow automation, task scheduling, and process orchestration.

**Hermes Reference Areas:**
- **Reference only:** Hermes process management and background task concepts (adapt to service interface)

**Butler-Native Implementation:**
- Workflow definition and execution engine
- Trigger-based automation (time, event, webhook)
- Task queuing and priority management
- Retry logic and failure handling
- Workflow monitoring and audit trails

**Dependencies:**
- Memory service (for workflow state)
- Tools service (for workflow execution steps)
- Orchestrator service (for decision logic in workflows)
- Config service (workflow configuration, schedules)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Workflow persistence and recovery
- Deadlock detection and prevention
- Resource limits and queue management
- Failure isolation (one workflow failure doesn't block others)
- Audit trail for all workflow executions

### 11. Device/IoT Service (8010) - Post-MVP

**Purpose:** Device and environment control, smart home integration.

**Hermes Reference Areas:**
- **Reference only:** Hermes device control and sensor tool concepts (adapt to service interface)

**Butler-Native Implementation:**
- Device discovery and registration
- Command and control interface
- Sensor data collection and processing
- Automation rules and scene management
- Firmware update and device management

**Dependencies:**
- Memory service (for device state and preferences)
- Tools service (for device communication protocols)
- Orchestrator service (for automation decision logic)
- Config service (device credentials, network configuration)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Device authentication and secure communication
- Command validation and safety interlocks
- State synchronization and conflict resolution
- Firmware verification and rollback mechanisms
- Network segmentation and access control

### 12. Observability Service (8011) - Post-MVP

**Purpose:** Metrics, logging, tracing, and system health monitoring.

**Hermes Reference Areas:**
- **Direct copy patterns:** `hermes_logging.py` for idempotent centralized logging, rotating handlers, and correlation/session context
- **Adapted copy:** `hermes_cli/logs.py` for log querying and filtering concepts (adapt to service API)
- **Reference only:** `hermes_cli/config.py` for logging configuration concepts

**Butler-Native Implementation:**
- Structured logging with trace IDs and span context
- Metrics collection and exposition (Prometheus format)
- Health checks and readiness probes
- Log aggregation and querying interface
- Alerting and notification system
- Performance profiling and bottleneck identification

**Dependencies:**
- All services (for telemetry collection)
- Config service (observability configuration, endpoints)
- Memory service (for historical metrics and traces)

**Execution Order:** Build early - observability should be available during development of other services

**Production Hardening:**
- Idempotent logging setup (safe to call multiple times)
- Log redaction for sensitive information
- Metrics cardinality limits and aggregation
- Health check dependencies and cascading failure prevention
- Alert fatigue prevention and suppression rules
- Log storage retention and archival policies

### 13. Data Analytics Service (8012) - Post-MVP

**Purpose:** Business intelligence, reporting, and data visualization.

**Hermes Reference Areas:**
- **Reference only:** Hermes analytics and reporting tool concepts (adapt to service interface)

**Butler-Native Implementation:**
- Event tracking and user behavior analysis
- Funnel analysis and conversion tracking
- Cohort analysis and retention metrics
- Custom report builder and dashboard builder
- Data export and API access for external tools

**Dependencies:**
- Memory service (for raw event data)
- Orchestrator service (for computed metrics and aggregates)
- Tools service (for data collection and processing)
- Config service (analytics configuration, retention policies)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Data privacy and anonymization techniques
- Query performance optimization and caching
- Data retention and deletion policies
- Access control and role-based permissions
- Data quality monitoring and validation

### 14. Security Service (8013) - Post-MVP

**Purpose:** Centralized security policy enforcement, threat detection, and incident response.

**Hermes Reference Areas:**
- **Reference only:** Hermes security tool concepts and auth.py concepts (adapt to service API)

**Butler-Native Implementation:**
- Centralized policy decision point for security checks
- Threat detection and anomaly detection
- Security event logging and alerting
- Incident response playbooks and automation
- Security scanning and vulnerability assessment
- Compliance reporting and audit trail generation

**Dependencies:**
- Auth service (for authentication and authorization checks)
- Memory service (for security event storage)
- Tools service (for external security API execution)
- Config service (security policies, thresholds, rules)
- Orchestrator service (for security decision logic in workflows)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Defense in depth and layered security approach
- Least privilege access control
- Secure default configurations
- Regular security scanning and penetration testing
- Incident response readiness and drills
- Security metrics and KPI tracking

### 15. Security Threat Detection Service (8014) - Post-MVP

**Purpose:** Real-time threat detection and behavioral analysis.

**Hermes Reference Areas:**
- **Reference only:** Hermes anomaly detection and monitoring tool concepts (adapt to service API)

**Butler-Native Implementation:**
- Behavioral baselining for users and entities
- Real-time anomaly detection and scoring
- Threat intelligence integration and IOC matching
- User and entity risk scoring
- Automated response and containment actions

**Dependencies:**
- Auth service (for user and entity identification)
- Memory service (for behavioral baselines and event storage)
- Tools service (for external threat intelligence feeds)
- Orchestrator service (for decision logic and response automation)
- Config service (detection thresholds, models, feeds)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Model drift detection and retraining triggers
- False positive reduction and tuning mechanisms
- Alert validation and escalation procedures
- Privacy-preserving analytics techniques
- Secure handling of sensitive threat data

### 16. Plugins Service (8015) - Post-MVP

**Purpose:** Plugin architecture, extension system, and third-party integration.

**Hermes Reference Areas:**
- **Reference only:** Hermes skills system and plugin concepts (adapt to service API)

**Butler-Native Implementation:**
- Plugin discovery and loading mechanism
- Interface contracts and versioning
- Sandboxing and isolation for untrusted plugins
- Plugin marketplace and distribution system
- Configuration management and dependency resolution

**Dependencies:**
- Memory service (for plugin state and configuration)
- Tools service (for plugin execution environment)
- Orchestrator service (for plugin integration points)
- Config service (plugin configuration, repositories, permissions)

**Execution Order:** Build after core services are stable

**Production Hardening:**
- Plugin sandboxing and privilege separation
- Code signing and integrity verification
- Dependency vulnerability scanning
- Resource limits and quota enforcement
- Plugin lifecycle management and cleanup

### 17. Security (Baseline) - Cross-cutting

**Purpose:** Foundational security controls that apply to all services.

**Hermes Reference Areas:**
- **Direct copy patterns:** `hermes_cli/config.py` for secure file/directory handling and permissioning
- **Adapted copy:** `hermes_logging.py` for secure logging with redaction
- **Reference only:** `docs/security/*` for policy and standards guidance

**Butler-Native Implementation:**
- TLS 1.3 for all transport (enforced at infrastructure level)
- mTLS for internal service communication
- AES-256-GCM for sensitive data at rest
- Argon2id for password hashing (already in Auth service)
- Envelope encryption for key hierarchy
- Data classification enforcement
- AI-specific protection against prompt injection, unsafe tool use, and memory poisoning
- Security headers and CSP for HTTP services
- Input validation and output encoding everywhere
- Dependency vulnerability scanning and updates

**Dependencies:**
- Config service (security policies, keys, certificates)
- Memory service (for audit logs and security events)
- Orchestrator service (for security decision logic)
- Tools service (for external security API execution)

**Execution Order:** Build first - security baseline should be in place before any service handles sensitive data

**Production Hardening:**
- No hardcoded secrets in any service
- No fake crypto in security-sensitive code paths
- No module-level mutable state for auth/session persistence
- No direct service-to-service coupling that bypasses security checks
- All security-sensitive helpers centralized and audited
- Regular security scanning and dependency updates
- Clear separation of duties and least privilege access

---

## Execution Sequencing Guidance

### Phase 0: Foundation (Weeks 0-1)
1. Security baseline implementation
2. Config service with raw-vs-resolved separation
3. Logging service with idempotent setup and correlation IDs
4. Auth service with PostgreSQL and Argon2id
5. Memory service with SQLite persistence

### Phase 1: MVP Core (Weeks 2-3) - 9 hours to working system
1. Orchestrator service with intent classification
2. Tools service with get_time and send_message
3. Gateway service with API contract and JWT validation
4. Docker-compose setup for all five services
5. Smoke test: login → chat → history

### Phase 2: Observability & Reliability (Weeks 4-5)
1. Observability service with metrics, logging, tracing
2. Health checks and readiness probes for all services
3. Circuit breaker and retry patterns
4. Graceful degradation patterns
5. Log aggregation and querying

### Phase 3: Extension Services (Weeks 6-12)
1. Realtime service with WebSocket support
2. ML service with embedding generation
3. Search service with web search capabilities
4. Communication service with external messaging
5. Workflows service with automation engine
6. Device/IoT service with smart home integration
7. Data analytics service with reporting capabilities
8. Security service with policy enforcement
9. Security threat detection service with behavioral analysis
10. Plugins service with extension system

### Phase 4: Hardening & Optimization (Weeks 13-16)
1. Performance optimization and bottleneck resolution
2. Security scanning and penetration testing
3. Chaos engineering and failure injection testing
4. Load testing and scalability validation
3. Documentation completeness and accuracy review
4. Backup and disaster recovery procedures
5. Compliance validation and certification preparation

---

## Risk Register (Hermes-Informed Butler Guardrails)

| Risk Area | Hermes Issue Pattern | Butler Guardrail | Verification Method |
|-----------|---------------------|------------------|---------------------|
| Config corruption / secret leakage | #4775 (config rewrites with resolved secrets) | Never persist resolved secrets back to config/state; keep raw env placeholders separate from resolved runtime settings | Attempt to write resolved secrets to config; verify only raw placeholders persist |
| Gateway startup ambiguity | #8620, #8475 (startup fails without clear surface) | Expose exact startup failure reason in logs and health output | Break config/dependency; verify health endpoint returns actionable reason |
| Message loss under load | #4947 (single-slot pending message overwrite) | Preserve ordered processing per session; never overwrite earlier pending work | Send rapid sequence of messages; verify all are processed in order |
| Observability duplication | Logging history shows non-idempotent setup | Initialize logging once; include correlation/request IDs in all logs | Call logging setup multiple times; verify no duplicate handlers or corrupted logs |
| Managed tool seam drift | Tool-gateway helpers show environment resolution can silently drift | Tool execution/config resolution must be explicit and test-backed | Change env/token at runtime; verify tool execution reflects changes explicitly |
| Silent failures | #816 (log handler duplication + recursion → infinite loop) | Fail startup loudly; add interrupt depth caps; sentinel guards for log handlers | Introduce fault condition; verify explicit failure reason, not silent hang |
| Secret leakage in logs | Various issues showing secrets in logs | Log redaction for sensitive information (passwords, tokens, keys) | Attempt to log sensitive data; verify it appears redacted in logs |
| Resource exhaustion | Unbounded queues, recursion, cache growth | Resource limits, timeouts, eviction policies, circuit breakers | Exhaust resource; verify graceful degradation, not crash |
| Inconsistent failure handling | Vague or missing error messages | Deterministic error responses with actionable reason strings | Trigger failure condition; verify error message helps operator diagnose and fix |
| Config file corruption | #5214 (locked/invalid config.yaml handling) | Graceful degradation when config is locked or corrupted; clear errors instead of silent failures | Make config read-only or corrupt; verify clear error message, not silent failure |
| Windows encoding issues | #7058 (UTF-8 encoding failure on Windows) | Always open config files with explicit UTF-8 encoding | Test on Windows; verify config loads correctly with UTF-8 characters |
| Memory stale overwrite | #2670 (memory flush agent overwrites live memory) | Append-only persistence for golden path; guard against stale overwrite patterns | Run memory flush with existing data; verify existing entries preserved |
| Tool execution drift | Implicit tool resolution that can change behavior | Explicit tool config resolution; never silently downgrade to fake success | Change tool config; verify execution changes explicitly, not implicitly |

---

## Verification Expectations for Full System

### Contract Verification
- [ ] All service APIs match their documented contracts exactly
- [ ] No service owns business logic that belongs to another service
- [ ] All dependencies are explicit and injected (no hardcoded imports)
- [ ] Health endpoints return actionable failure reasons when unhealthy
- [ ] Correlation/request IDs appear in logs and traces for all requests

### Security Verification
- [ ] No hardcoded secrets in any service code or config
- [ ] All passwords use Argon2id hashing (where applicable)
- [ ] JWT tokens have proper claims, expiry, and validation
- [ ] TLS 1.3 enforced for all transport
- [ ] mTLS used for internal service communication
- [ ] AES-256-GCM for sensitive data at rest
- [ ] Envelope encryption for key hierarchy
- [ ] Data classification labels applied and enforced
- [ ] AI-specific protections (prompt injection, unsafe tool use, memory poisoning)

### Reliability Verification
- [ ] Services degrade gracefully when dependencies unavailable
- [ ] Resource limits prevent exhaustion (memory, CPU, file descriptors)
- [ ] Timeouts and retry logic prevent hanging requests
- [ ] Circuit breakers prevent cascading failures
- [ ] Health checks detect and report dependency failures
- [ ] Log redaction prevents sensitive information leakage
- [ ] Backup and restore procedures work for all persistent state

### Observability Verification
- [ ] Idempotent logging setup (safe to call multiple times)
- [ ] Structured logging with trace IDs and span context
- [ ] Metrics collection and exposition in standard format
- [ ] Health checks and readiness probes for all services
- [ ] Alerting rules fire appropriately and include context
- [ ] Log querying and filtering works as expected
- [ ] Performance profiling identifies bottlenecks
- [ ] Distributed tracing shows request flow across services

### Operational Verification
- [ ] All services can be started, stopped, and restarted independently
- [ ] Configuration changes can be applied without restart (where appropriate)
- [ ] Database migrations work correctly
- [ ] Rolling updates work for stateless services
- [ ] Backup procedures capture all necessary state
- [ ] Disaster recovery procedures restore system to known good state
- [ ] Security patches can be applied without downtime
- [ ] Dependency updates can be tested and rolled back

---

## Implementation Notes for Multi-Agent Execution System

### Task Granularity
- Each service should be broken into 2-5 minute actionable tasks
- Each task must touch a clear set of files/functions with explicit verification
- No vague tasks like "implement service X" - must be specific like "add validate_jwt() to auth/service.py that checks signature and expiration"

### Dependency Management
- Services should be implementable in isolation with mocked dependencies
- Interface contracts should be defined before implementation
- Breaking changes should require explicit version bump and migration path

### Testing Strategy
- Unit tests for individual functions and classes
- Integration tests for service-to-service interactions
- End-to-end tests for golden path and critical user journeys
- Chaos engineering tests for failure scenarios
- Performance tests for load and stress conditions

### Documentation Requirements
- Every service spec must include: overview, responsibilities, boundaries, dependencies, API contracts, data flow, core logic, failure handling, security notes, scaling notes, observability expectations
- Every implementation must be traceable back to source documentation
- When code and docs disagree, either the code is wrong or the doc must be updated before code is considered correct

### Quality Gates
- No service considered complete until:
  - Its spec is complete (all required sections present)
  - Its implementation matches its spec
  - Its unit tests pass (≥90% coverage)
  - Its integration tests pass
  - Its end-to-end tests pass for critical paths
  - Its production hardening measures are in place and verified
  - Its observability is sufficient to diagnose failures without source inspection
  - Its security baseline controls are verified

### Rollback and Recovery
- Every change must be backward compatible or have explicit migration path
- Database migrations must be tested and reversible
- Configuration changes must be validatable before application
- Service restarts must not lose in-flight requests (where applicable)
- Failed deployments must be automatically rolled back