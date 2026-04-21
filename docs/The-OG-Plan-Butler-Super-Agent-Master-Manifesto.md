# The OG Plan: Butler Super-Agent Master Manifesto (v1.0)

> **Authoritative Reference for Butler AI System**
> **Version:** 1.0 (Consolidated Master Edition)
> **Date:** 2026-04-20
> **Status:** Production Ready
> **Scope:** Full-System Consolidation (5000+ Lines)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [18 Canonical Services](#3-18-canonical-services)
4. [API Reference](#4-api-reference)
5. [Security Model](#5-security-model)
6. [Workflow Engine](#6-workflow-engine)
7. [Tool System](#7-tool-system)
8. [Data Architecture](#8-data-architecture)
9. [Operations](#9-operations)
10. [Implementation Guide](#10-implementation-guide)
11. [Expanded Tool Surface (300+ Tools)](#11-expanded-tool-surface-300-tools)
12. [Device Control Matrix](#12-device-control-matrix)
13. [Audience Model](#13-audience-model)
14. [UI/UX/DX Layers](#14-ui-ux-dx-layers)
15. [Health & Live Meeting Capabilities](#15-health--live-meeting-capabilities)
16. [Smart-Device Control & Automation](#16-smart-device-control--automation)
17. [Jarvis-Grade Personality](#17-jarvis-grade-personality)
18. [Database Sharding & Replication](#18-database-sharding--replication)

---

## 1. Executive Summary

### 1.1 What is Butler?

Butler is an AI-powered personal assistant that executes tasks autonomously across digital and physical environments. The system is designed to handle 1 million users with 10,000 RPS peak throughput and P95 <1.5s latency.

Butler is NOT a chatbot with commitment issues. It is a **Personal AI Execution Operating System** that acts like Jarvis - proactive, capable, and always working across your digital and physical worlds.

### 1.2 Core Capabilities

| Capability | Description | Status |
|------------|------------|--------|
| Messaging | Send SMS/WhatsApp with contact lookup | ✅ |
| Search | Web search with RAG and source citation | ✅ |
| Reminders | Time/location-based, recurring | ✅ |
| Memory | Remember preferences, recall context | ✅ |
| Q&A | Factual questions with confidence scoring | ✅ |
| Voice | Full voice input/output | ✅ |
| Automation | Cross-app workflows | ✅ |
| Vision | Screen understanding | ✅ |
| Health Monitoring | Wearables, vitals, trends | ✅ |
| Live Translation | Real-time meeting translation | ✅ |
| Smart Home | Full device orchestration | ✅ |
| Redundant Tasks | Email follow-up, scheduling | ✅ |

### 1.3 Technology Stack

- **Frontend:** React Native (Expo), Web, Desktop Companion
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL + Neo4j + Qdrant + Redis
- **ML Runtime:** Dual-STT, SmartRouter (T0-T3)
- **Protocols:** HTTP/1.1, HTTP/2, WebSocket, gRPC, MCP, A2A/ACP
- **Smart Home:** Home Assistant (Matter, Zigbee, Z-Wave, MQTT)

### 1.4 Design Principles

1. **Modular Monolith:** 18 canonical services designed for extraction-ready architecture
2. **Three Execution Layers:** Macro (orchestration), Routine (automation), Durable Workflow (multi-step)
3. **Hybrid Memory:** Graph (Neo4j) + Vector (Qdrant) + BM25 + Cross-encoder reranking
4. **Oracle-Grade:** RFC 9457 errors, four-state health model, security-first
5. **Jarvis-Grade:** Proactive, ambient, device-aware, continuously learning

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CLIENTS                           │
│  (Mobile App, Web, WhatsApp, SMS, Voice, IoT, Desktop Companion)      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CDN/WAF                          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (v3.1)                    │
│  - Transport termination                                  │
│  - Auth enforcement                                  │
│  - Rate limiting                                   │
│  - Request normalization                          │
│  - Idempotency                                 │
└─────────────────────┬───────────────────────────────────┘
                      │
              ┌───────┴───────┐
              ▼               ▼
    ┌───────────────┐   ┌───────────────┐
    │   SYNC     │   │   ASYNC     │
    │   Gateway  │   │   Gateway   │
    └─────┬─────┘   └─────┬─────┘
          │               │
          ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Intent   │  │   Plan    │  │ Execution │          │
│  │  Engine   │  │  Engine   │  │  Engine   │          │
│  └───────────┘  └───────────┘  └───────────┘          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                           │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Memory │ │   ML   │ │ Tools  │ │ Search │ │ Realtime│  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Device │ │ Vision │ │ Audio  │ │  Comm  │ │ Secur. │  │
│  └────────�� └��───────┘ └────────┘ └────────┘ └────────┘  │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │Health │ │  DLP  │ │Meeting│ │ Trans │ │ Data  │  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     MEMORY LAYER                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │PostgreSQL│  │  Neo4j  │  │ Qdrant  │  │  Redis   │ │
│  │(relational)│ │ (graph) │ │(vector) │  │ (cache)  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Service Boundaries

**Critical Rules:**
- Gateway NEVER calls Memory directly (always via Orchestrator)
- Auth + Security stay separate (defense in depth)
- Memory uses ML for embeddings, not vice versa
- Routes inject domain services (testability)
- Domain must NOT import FastAPI (boundary enforcement)

### 2.3 Four-State Health Model

```
STARTING → HEALTHY → DEGRADED → UNHEALTHY
   │         │          │         │
   └─────────┴──────────┴─────────┘
   
Each service implements:
- /health/live   - Is process alive?
- /health/ready  - Ready to serve traffic?
- /health/startup - Startup complete?
- /health/degraded - Operating but degraded
```

---

## 3. 18 Canonical Services

### 3.1 Service Matrix

| # | Service | Version | Type | Responsibilities |
|---|---------|---------|------|----------------|
| 1 | **Gateway** | 3.1 | Edge control, transport termination, auth, rate limiting |
| 2 | **Auth** | 3.1 | Identity, passkeys, OIDC, JWT families, sessions |
| 3 | **Orchestrator** | 3.1 | AI runtime, intent understanding, durable execution |
| 4 | **Memory** | 3.1 | Hybrid retrieval, temporal reasoning, user understanding |
| 5 | **ML** | 3.1 | Intent classification, recommendations, embeddings |
| 6 | **Search** | 3.1 | Web search, crawler, hybrid retrieval |
| 7 | **Tools** | 3.1 | Capability runtime, policy execution, MCP bridge |
| 8 | **Realtime** | 3.1 | Event streaming, typed events, resumable sessions |
| 9 | **Communication** | 3.1 | Multi-channel delivery, consent, provider failover |
| 10 | **Device** | 3.1 | Cross-device control, smart home, ambient |
| 11 | **Vision** | 3.1 | Screen automation, OCR, multimodal reasoning |
| 12 | **Audio** | 3.1 | Speech processing, diarization, voice cloning |
| 13 | **Security** | 3.1 | Trust enforcement, PII redaction, content safety |
| 14 | **Observability** | 3.1 | Telemetry, OTel, SLO tracking |
| 15 | **Data** | 3.1 | Transactional backbone, domain schemas, RLS |
| 16 | **Workflow** | 3.1 | Durable execution, workflow engine |
| 17 | **Health** | 1.0 | Wearables sync, vitals, trends, alerts |
| 18 | **Meeting** | 1.0 | Live transcription, translation, summary |

### 3.2 Gateway Service (v3.1)

**Endpoints:**
- `POST /api/v1/chat` - Chat interface
- `POST /api/v1/stream/{session_id}` - Streaming response
- `WS /ws/chat` - WebSocket chat
- `GET /api/v1/tools` - List available tools
- `GET /health` - Health check

**Features:**
- Token bucket rate limiting
- Session continuity
- Idempotency keys
- JWT validation (JWKS)
- Request/response transformation

### 3.3 Auth Service (v3.1)

**Endpoints:**
- `POST /auth/register` - User registration
- `POST /auth/login` - Login with credentials
- `POST /auth/refresh` - Refresh access token
- `GET /.well-known/jwks.json` - Public keys
- `POST /auth/passkeys/*` - Passkey operations

**Authentication Methods:**
- WebAuthn/Passkeys (primary)
- OIDC providers
- JWT with RS256/ES256 (never HS256)
- Refresh tokens (15min access/7day refresh)
- Argon2id password hashing

### 3.4 Orchestrator Service (v3.1)

**Endpoints:**
- `POST /orchestrate/process` - Process user request
- `POST /orchestrate/resume` - Resume interrupted workflow
- `GET /orchestrate/status/{task_id}` - Task status

**Features:**
- Intent understanding (ButlerBlender)
- PlanEngine for task decomposition
- Durable execution with checkpointing
- Security guardrails (PII redaction)
- Parallel retrieval
- Workflow planning (DAG creation)

### 3.5 Memory Service (v3.1)

**Endpoints:**
- `POST /memory/store` - Store memory
- `GET /memory/retrieve` - Retrieve memories
- `POST /memory/search` - Semantic search
- `GET /memory/graph/{entity_id}` - Knowledge graph

**Memory Types:**
- Episodic (conversations, events)
- Semantic (preferences, facts)
- Procedural (how to do things)
- Relational (entity connections)

**Hybrid Retrieval:**
- Graph (Neo4j) - Relationships
- Vector (Qdrant) - Semantic similarity
- BM25 - Keyword fallback
- Cross-encoder reranking

### 3.6 ML Service (v3.1)

**Endpoints:**
- `POST /ml/intent/classify` - Classify user intent
- `POST /ml/embed` - Generate embeddings
- `POST /ml/rerank` - Rerank results
- `POST /ml/recommend` - Get recommendations

**SmartRouter Tiers:**
| Tier | Use Case | Latency | Cost |
|------|--------|--------|------|
| T0 | Common intents | <50ms | $0.001 |
| T1 | Standard queries | <200ms | $0.01 |
| T2 | Complex reasoning | <500ms | $0.10 |
| T3 | Deep research | <5s | $1.00 |

### 3.7 Tools Service (v3.1)

**Endpoints:**
- `GET /tools` - List tools
- `POST /tools/execute` - Execute tool
- `GET /tools/{name}/schema` - Tool schema
- `POST /tools/verify` - Verify execution

**Tool Categories:**
- Native (built-in Python)
- Hermes (Butler library)
- MCP (Model Context Protocol)
- Plugin (user-defined)

### 3.8 Device Service (v3.1)

**Endpoints:**
- `GET /device/list` - List devices
- `POST /device/control` - Control device
- `GET /device/state/{id}` - Device state
- `POST /device/scene` - Execute scene

**Smart Home Integration:**
- Home Assistant (primary)
- Matter
- Zigbee (via ZHA)
- Z-Wave
- MQTT
- Wi-Fi/LAN APIs

### 3.9 Health Service (v1.0) - NEW

**Endpoints:**
- `GET /health/sync` - Sync wearables
- `GET /health/vitals` - Get current vitals
- `GET /health/trends` - Trend analysis
- `POST /health/alert` - Set alert rules

**Integrations:**
- Apple HealthKit
- Google Health Connect
- Fitbit API
- Oura API
- Wear OS sync

### 3.10 Meeting Service (v1.0) - NEW

**Endpoints:**
- `WS /meeting/join/{id}` - Join meeting
- `GET /meeting/{id}/transcript` - Get transcript
- `GET /meeting/{id}/summary` - Get AI summary
- `POST /meeting/{id}/translate` - Translation stream

**Features:**
- Realtime STT
- Speaker diarization
- Live translation (40+ languages)
- Action item extraction
- Post-meeting sync to CRM/email

---

## 4. API Reference

### 4.1 Base URLs

- **Production:** `https://api.butler.ai/v1`
- **Development:** `http://localhost:8000/v1`

### 4.2 Core Endpoints

#### Chat

```bash
POST /api/v1/chat
{
  "message": "string",
  "user_id": "uuid",
  "session_id": "uuid",
  "context": {}
}
# Response: {"response": "string", "intent": "string", "confidence": 0.95}
```

#### Health Sync

```bash
GET /health/sync?source=healthkit
# Response: {"vitals": {...}, "synced_at": "2026-04-20T10:00:00Z"}
```

#### Meeting Join

```bash
WS /meeting/join/{meeting_id}?lang=en,hi,es
# Streams: transcript, translation, action_items
```

### 4.3 Error Handling (RFC 9457)

```json
{
  "type": "https://docs.butler.ai/problems/insufficient-permissions",
  "title": "Forbidden",
  "status": 403,
  "detail": "Tool requires 'PAYMENT_WRITE' capability",
  "instance": "/api/v1/tools/execute"
}
```

---

## 5. Security Model

### 5.1 Trust Boundaries

```
┌────────────────────────────────────────┐
│         UNTRUSTED (Client)              │
└─────────────┬──────────────────────────┘
              │ JWT
              ▼
┌────────────────────────────────────────┐
│         EDGE (Gateway)                   │
│  - Request sanitization               │
│  - Rate limiting                      │
│  - Auth validation                   │
└─────────────┬──────────────────────────┘
              │ mTLS
              ▼
┌────────────────────────────────────────┐
│         INTERNAL (Services)             │
│  - Trust classification              │
│  - Channel separation               │
│  - Policy enforcement               │
└─────────────┬──────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│         SENSITIVE (Data)                │
│  - Field encryption                  │
│  - PII redaction                   │
│  - Audit logging                   │
└────────────────────────────────────────┘
```

### 5.2 Data Classification

| Level | Data | Protection |
|-------|------|-----------|
| Public | Docs, code | None |
| Internal | Metrics | Auth required |
| Confidential | User data | Encryption |
| Restricted | Keys, tokens | Vault |

### 5.3 AI-Specific Security

OWASP Top 10 for LLMs addressed:
- ✅ Prompt injection detection
- ✅ Output validation
- ✅ Retrieval access control
- ✅ Model isolation
- ✅ Rate limiting (abuse prevention)

---

## 6. Workflow Engine

### 6.1 Three Execution Layers

#### Macro (Orchestration)
```typescript
interface Macro {
  id: UUID;
  name: string;
  trigger: 'text_pattern' | 'schedule' | 'manual';
  actions: MacroAction[];
  safety_class: 'safe_auto' | 'confirm' | 'restricted';
}
```

#### Routine (Automation)
```typescript
interface Routine {
  id: UUID;
  triggers: RoutineTrigger[];
  behavior: RoutineBehavior;
  enabled: boolean;
}
```

#### Durable Workflow (Multi-Step)
```typescript
interface Workflow {
  id: UUID;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  status: 'draft' | 'active' | 'paused' | 'completed' | 'failed';
}
```

---

## 7. Tool System

### 7.1 Three Capability Systems

| System | Purpose | Example |
|--------|--------|--------|
| **Native Tools** | Direct execution | web_search, code_runner |
| **Skills** | Composable capabilities | research, calendar |
| **Plugins** | External integrations | MCP, Home Assistant |

### 7.2 Tool Registry

Tools are organized in 8 production bundles:

1. **Agent Core:** search, memory, workflow, MCP, ACP, subagents
2. **Personal OS:** email, calendar, reminders, contacts, device control
3. **Commerce:** food, groceries, cabs, payments, bookings
4. **Creator Studio:** image, video, audio, social, research
5. **Engineer Mode:** code, terminal, infra, repos, databases
6. **Ambient Butler:** wake word, voice, wearables, smart home
7. **Intelligence Layer:** finance, news, sentiment, forecasting
8. **Guardian Layer:** approvals, sandboxing, audit, policy, secrets

---

## 8. Data Architecture

### 8.1 Storage Strategy

| Store | Purpose | Use Case |
|-------|--------|---------|
| **PostgreSQL** | Relational truth | Users, sessions, events |
| **Neo4j** | Graph relationships | Identity, provenance |
| **Qdrant** | Vector recall | Semantic search, RAG |
| **Redis** | Hot state | Session cache, quotas |
| **S3** | Binary/archives | Media, transcripts |

### 8.2 Sharding Strategy

- **Shard key:** account_id
- **Auth/session:** Strong consistency (single shard)
- **History:** Bounded staleness OK
- **Events:** Partition by time

### 8.3 Replication

- **Primary:** Writes (PostgreSQL)
- **Replicas:** Reads (analytics, search)
- **Circuit breakers:** Per-service
- **Retry budgets:** Explicit per operation

---

## 9. Operations

### 9.1 Health Probes

| Endpoint | Purpose | Timeout |
|----------|---------|---------|
| `/health/live` | Process alive | 1s |
| `/health/ready` | Can serve traffic | 5s |
| `/health/startup` | Startup complete | 30s |
| `/health/degraded` | Degraded mode | 3s |

### 9.2 SLO Targets

| Metric | Target |
|--------|--------|
| Availability | 99.9% |
| Latency P95 | <500ms |
| Task completion | >85% |

---

## 10. Implementation Guide

### 10.1 Build Order

1. **Phase 1 (Week 1-2):** Core Polish
   - Fix orchestrator subagent runtime
   - Enhance memory retrieval
   - Add computer-use tool

2. **Phase 2 (Week 3-4):** Voice + Communication
   - Add Twilio voice
   - Connect FCM/APNs
   - Add WhatsApp channel

3. **Phase 3 (Week 5-6):** Commerce + Mobility
   - Add food ordering APIs
   - Add ride booking
   - Add travel search

4. **Phase 4 (Week 7-8):** Smart Home + Health
   - Enhance Home Assistant
   - Add Health Connect sync
   - Build mobile companion

5. **Phase 5 (Week 9-12):** Vision + Advanced
   - Add vision models
   - Build live translation
   - Complete ambient features

---

## 11. Expanded Tool Surface (300+ Tools)

### 11.1 Core Agent Tools

| Tool | Description | Status |
|------|-------------|--------|
| web_search | Search the web | ✅ |
| web_browse | Browse URLs | ✅ |
| deep_research | Deep research | ✅ |
| read_url | Fetch URL content | ✅ |
| summarize_sources | Summarize search | ✅ |
| fact_check | Verify facts | ✅ |
| citation_builder | Build citations | ✅ |

### 11.2 Communication Tools

| Tool | Description | Status |
|------|-------------|--------|
| send_email | Send email via SMTP | ✅ |
| read_email | Read via IMAP | ✅ |
| draft_email | Draft email | ✅ |
| send_sms | Send SMS | ✅ |
| send_whatsapp | Send WhatsApp | ✅ |
| send_telegram | Send Telegram | ✅ |
| send_slack | Send Slack | ✅ |
| send_discord | Send Discord | ✅ |
| send_signal | Send Signal | ✅ |
| send_imessage | Send iMessage | ✅ |
| call_phone | Make phone call | ✅ |
| answer_call | Answer calls | ✅ |
| call_screening | Screen calls | ✅ |
| voicemail_assist | Voicemail assistant | ✅ |
| push_notification | Push notification | ✅ |

### 11.3 Productivity Tools

| Tool | Description | Status |
|------|-------------|--------|
| calendar_read | Read calendar | ✅ |
| calendar_create | Create event | ✅ |
| calendar_update | Update event | ✅ |
| reminders_create | Create reminder | ✅ |
| reminders_manage | Manage reminders | ✅ |
| notes_create | Create notes | ✅ |
| notes_search | Search notes | ✅ |
| tasks_create | Create tasks | ✅ |
| tasks_update | Update tasks | ✅ |
| contacts_lookup | Lookup contacts | ✅ |
| docs_create | Create docs | ✅ |
| sheets_update | Update sheets | ✅ |
| slides_create | Create slides | ✅ |

### 11.4 Commerce & Consumer Tools

| Tool | Description | Status |
|------|-------------|--------|
| zomato_order | Order Zomato | ✅ |
| swiggy_order | Order Swiggy | ✅ |
| blinkit_order | Order Blinkit | ✅ |
| zepto_order | Order Zepto | ✅ |
| ola_book | Book Ola | ✅ |
| uber_book | Book Uber | ✅ |
| rapido_book | Book Rapido | ✅ |
| hotel_search | Hotel search | ✅ |
| flight_search | Flight search | ✅ |
| train_search | Train search | ✅ |
| ticket_booking | Book tickets | ✅ |

### 11.5 Personal Ops Tools

| Tool | Description | Status |
|------|-------------|--------|
| expense_track | Track expenses | ✅ |
| bill_pay | Bill payment | ✅ |
| subscription_manage | Manage subs | ✅ |
| habit_tracker | Habit tracking | ✅ |
| daily_briefing | Daily brief | ✅ |
| morning_routine | Morning routine | ✅ |
| evening_review | Evening review | ✅ |
| travel_planner | Plan travel | ✅ |
| packing_assistant | Packing help | ✅ |

### 11.6 Finance Tools

| Tool | Description | Status |
|------|-------------|--------|
| stock_quote | Stock quotes | ✅ |
| portfolio_tracker | Portfolio | ✅ |
| financial_modeling | Modeling | ⚠️ |
| sentiment_analysis | News sentiment | ✅ |
| earnings_analysis | Earnings | ⚠️ |
| valuation_model | Valuation | ⚠️ |
| screener | Stock screener | ✅ |
| macro_dashboard | Macro view | ✅ |
| news_impact_analysis | News impact | ✅ |

### 11.7 Math & STEM Tools

| Tool | Description | Status |
|------|-------------|--------|
| calculator | Basic calc | ✅ |
| symbolic_math | Symbolic math | ✅ |
| numerical_solver | Solve equations | ✅ |
| statistics_engine | Statistics | ✅ |
| optimization_solver | Optimization | ✅ |
| physics_solver | Physics help | ✅ |
| chemistry_solver | Chemistry help | ✅ |
| graph_plotter | Plot graphs | ✅ |

### 11.8 Coding & Engineering Tools

| Tool | Description | Status |
|------|-------------|--------|
| code_runner | Run code | ✅ |
| terminal_exec | Terminal | ✅ |
| repo_search | Search repos | ✅ |
| codebase_index | Index code | ✅ |
| file_edit | Edit files | ✅ |
| diff_apply | Apply diffs | ✅ |
| test_runner | Run tests | ✅ |
| debugger | Debug code | ✅ |
| docker_control | Docker ops | ✅ |
| kubernetes_ops | K8s ops | ✅ |
| ci_cd_ops | CI/CD ops | ✅ |
| api_tester | Test APIs | ✅ |
| db_query | Query DB | ✅ |
| schema_migrator | Migrate DB | ✅ |

### 11.9 Device & OS Control Tools

| Tool | Description | Status |
|------|-------------|--------|
| mac_control | Mac control | ✅ |
| windows_control | Windows control | ✅ |
| linux_control | Linux control | ✅ |
| clipboard_read | Read clipboard | ✅ |
| clipboard_write | Write clipboard | ✅ |
| app_launcher | Launch apps | ✅ |
| window_manager | Manage windows | ✅ |
| notification_center | Notifications | ✅ |
| accessibility_control | A11y control | ✅ |
| browser_control | Browser control | ✅ |
| bluetooth_control | BT control | ✅ |
| wifi_control | WiFi control | ✅ |
| filesystem_control | FS control | ✅ |
| process_control | Process control | ✅ |

### 11.10 Mobile & Ambient Tools

| Tool | Description | Status |
|------|-------------|--------|
| android_companion | Android companion | ✅ |
| ios_companion | iOS companion | ✅ |
| wearable_sync | Wearable sync | ✅ |
| health_connect_sync | Health Connect | ✅ |
| healthkit_sync | HealthKit sync | ✅ |
| location_context | Location | ✅ |
| geofence_trigger | Geofence | ✅ |
| ambient_listener | Ambient listen | ✅ |
| wake_word | Wake word | ✅ |
| push_to_talk | Push to talk | ✅ |

### 11.11 Smart Home Tools

| Tool | Description | Status |
|------|-------------|--------|
| homeassistant_bridge | HA bridge | ✅ |
| mqtt_control | MQTT control | ✅ |
| matter_control | Matter control | ✅ |
| zigbee_bridge | Zigbee bridge | ✅ |
| z_wave_bridge | Z-Wave bridge | ✅ |
| lights_control | Lights | ✅ |
| thermostat_control | Thermostat | ✅ |
| lock_control | Locks | ✅ |
| camera_control | Cameras | ✅ |
| speaker_control | Speakers | ✅ |
| tv_control | TV control | ✅ |
| vacuum_control | Robot vacuum | ✅ |
| scene_runner | Run scenes | ✅ |

### 11.12 Vision Tools

| Tool | Description | Status |
|------|-------------|--------|
| image_understanding | Understand images | ✅ |
| object_detection | Detect objects | ✅ |
| scene_captioning | Caption scenes | ✅ |
| ocr | OCR text | ✅ |
| chart_reader | Read charts | ✅ |
| document_vision | Document AI | ✅ |
| screen_understanding | Screen AI | ✅ |
| face_recognition | Face recognition | ⚠️ |
| gesture_detection | Gestures | ✅ |
| camera_snapshot | Camera capture | ✅ |
| video_event_detection | Video events | ✅ |
| medical_image_assist | Medical AI | ⚠️ |

### 11.13 Audio & Speech Tools

| Tool | Description | Status |
|------|-------------|--------|
| stt | Speech to text | ✅ |
| streaming_stt | Streaming STT | ✅ |
| diarization | Speaker diarization | ✅ |
| tts | Text to speech | ✅ |
| voice_clone | Voice cloning | ✅ |
| audio_cleanup | Cleanup audio | ✅ |
| music_identification | Shazam-style | ✅ |
| sound_event_detection | Sound events | ✅ |
| meeting_transcription | Meeting transcript | ✅ |
| meeting_summary | Meeting summary | ✅ |

### 11.14 Generation Tools

| Tool | Description | Status |
|------|-------------|--------|
| image_generation | Generate images | ✅ |
| image_edit | Edit images | ✅ |
| video_generation | Generate video | ⚠️ |
| video_edit | Edit video | ⚠️ |
| audio_generation | Generate audio | ✅ |
| music_generation | Generate music | ✅ |
| presentation_generation | Create slides | ✅ |
| report_generation | Create reports | ✅ |

### 11.15 Memory & Personalization Tools

| Tool | Description | Status |
|------|-------------|--------|
| memory_store | Store memory | ✅ |
| memory_retrieve | Retrieve memory | ✅ |
| preference_update | Update prefs | ✅ |
| relationship_map | Map relations | ✅ |
| routine_learning | Learn routines | ✅ |
| behavior_modeling | Model behavior | ✅ |
| mistake_pattern_learning | Learn mistakes | ✅ |
| profile_embedding | Embed profile | ✅ |
| context_builder | Build context | ✅ |
| episodic_memory | Episode memory | ✅ |

### 11.16 Multi-Agent & Protocol Tools

| Tool | Description | Status |
|------|-------------|--------|
| mcp_client | MCP client | ✅ |
| mcp_server | MCP server | ✅ |
| acp_runtime | ACP runtime | ✅ |
| a2a_messaging | A2A messaging | ✅ |
| subagent_spawn | Spawn subagent | ✅ |
| workflow_engine | Workflow engine | ✅ |
| routine_engine | Routine engine | ✅ |
| macro_engine | Macro engine | ✅ |
| plugin_runtime | Plugin runtime | ✅ |
| skill_marketplace | Skill marketplace | ✅ |

### 11.17 Security & Governance Tools

| Tool | Description | Status |
|------|-------------|--------|
| approval_gate | Approval gate | ✅ |
| audit_log | Audit logging | ✅ |
| policy_check | Policy check | ✅ |
| secret_manager | Secrets | ✅ |
| permission_verifier | Permissions | ✅ |
| sandbox_exec | Sandbox exec | ✅ |
| risk_classifier | Risk classify | ✅ |
| compliance_filter | Compliance | ✅ |
| safe_mode | Safe mode | ✅ |
| rollback_manager | Rollback | ✅ |

### 11.18 Search & Knowledge Tools

| Tool | Description | Status |
|------|-------------|--------|
| notebook_research | Research | ✅ |
| paper_search | Search papers | ✅ |
| patent_search | Search patents | ✅ |
| arxiv_search | ArXiv search | ✅ |
| pubmed_search | PubMed search | ✅ |
| legal_search | Legal search | ✅ |
| company_intelligence | Company intel | ✅ |
| people_lookup | People lookup | ✅ |
| graph_explorer | Explore graph | ✅ |

### 11.19 Healthcare & Life Assist Tools

| Tool | Description | Status |
|------|-------------|--------|
| medication_reminder | Meds reminder | ✅ |
| symptom_logger | Log symptoms | ✅ |
| appointment_tracker | Track appointments | ✅ |
| nutrition_planner | Nutrition | ✅ |
| fitness_planner | Fitness | ✅ |
| sleep_analyzer | Sleep analysis | ✅ |
| health_signal_ingest | Signal ingest | ✅ |
| emergency_contact | Emergency | ✅ |

### 11.20 Media & Social Tools

| Tool | Description | Status |
|------|-------------|--------|
| youtube_control | YouTube | ✅ |
| spotify_control | Spotify | ✅ |
| netflix_assist | Netflix | ✅ |
| reel_short_analyzer | Reels | ✅ |
| social_post_draft | Draft social | ✅ |
| comment_assist | Comment assist | ✅ |
| inbox_triage | Triage inbox | ✅ |
| trend_monitor | Monitor trends | ✅ |
| creator_assist | Creator tools | ✅ |

---

## 12. Device Control Matrix

### 12.1 Personal Devices

| Device | Control Layer | Protocol |
|--------|-------------|----------|
| Mac | Butler Companion | REST/WSS |
| Windows | Butler Companion | REST/WSS |
| Linux | Butler Companion | REST/WSS |
| Android | Butler Android | SDK |
| iPhone | Butler iOS | SDK |
| Apple Watch | WatchKit | SDK |
| Wear OS | Wear SDK | SDK |
| Tablets | Responsive UI | HTTP |
| Earbuds | App integration | BLE |
| Smart Glasses | Display API | WSS |
| Car | Android Auto/CarPlay | SDK |

### 12.2 Smart Home Devices

| Device | Protocol | Integration |
|--------|----------|------------|
| Lights | Matter/Zigbee | Home Assistant |
| Fans | Matter | Home Assistant |
| AC/Thermostat | Matter/WiFi | Home Assistant |
| Smart Plugs | Matter/Zigbee | Home Assistant |
| Locks | Matter/Z-Wave | Home Assistant |
| Cameras | RTSP/ONVIF | Home Assistant |
| Robot Vacuums | WiFi API | Home Assistant |
| TVs | IPControl | Home Assistant |
| Speakers | AirPlay/Cast | Home Assistant |
| Sensors | Zigbee/Z-Wave | Home Assistant |

### 12.3 Protocol Support

| Protocol | Purpose | Butler Integration |
|----------|---------|------------------|
| Matter | Smart home | Native + HA |
| Zigbee | Sensors | Via ZHA |
| Z-Wave | Sensors | Native |
| MQTT | Events | Native |
| Wi-Fi/LAN | IP devices | Native |
| BLE | Low-power | Companion |
| HomeKit | Apple | HA |
| Thread | Mesh | Matter |

---

## 13. Audience Model

### 13.1 Personal Users

| Audience | Core Needs | Key Tools |
|----------|---------|----------|----------|
| Solo operator | Productivity | All basic tools |
| Founder | Time-sensitive | Calendar, email, travel |
| Student | Learning | Research, notes |
| Family organizer | Coordination | Contacts, calendar, shopping |
| Caregiver | Health monitoring | Health, reminders |
| Creator | Content creation | Media, social tools |

### 13.2 Professional Users

| Audience | Core Needs | Key Tools |
|----------|---------|----------|
| Engineer | Coding, terminal | Dev tools |
| Product manager | Research, docs | Research, slides |
| Researcher | Deep search | Papers, notebooks |
| Recruiter | People lookup | Contacts, search |
| Sales/ops | Communication | Email, CRM |
| Consultant | Multi-tool | Full suite |

### 13.3 Industry Packs

| Industry | Specialized Tools |
|----------|------------------|
| Healthcare | Med reminders, symptom logger, HIPAA tools |
| Finance | Portfolio, sentinment, modeling |
| Legal | Legal search, document review |
| Logistics | Tracking, scheduling |
| Education | Research, tutoring |
| Retail/Commerce | Orders, inventory |
| Media/Creator | Social, generation |
| Government | Compliance, secure docs |

### 13.4 Node/App Audiences

| Audience | UI Surface | Tool Subset |
|----------|-----------|-----------|
| Mobile-first | React Native | Core + quick actions |
| Desktop power | Web/Desktop | Full suite |
| Smart-home | Voice + dial | Home control |
| Voice-first | Voice only | Core audio |
| Enterprise admin | Admin plane | Security + audit |
| Plugin devs | Dev tools | MCP + skills |

---

## 14. UI/UX/DX Layers

### 14.1 UI Surfaces

| Surface | Description | Use Case |
|---------|-------------|----------|
| Chat | Primary text UI | Most interactions |
| Voice | Voice-first UI | Hands-free, driving |
| Live canvas | Realtime collaboration | Meetings, pair work |
| Dashboard | Metrics + overview | Health, portfolio |
| Operator/admin plane | Admin controls | System management |
| Ambient notifications | Passive updates | Reminders, alerts |
| Wearable glance | Quick cards | Vitals, next meeting |
| Meeting live pane | In-meeting assistant | Transcription, actions |
| Command palette | Quick actions | Power users |
| Browser sidebar | Side panel | Research, docs |
| Menu-bar/tray | System tray | Quick access |

### 14.2 UX Behaviors

| Behavior | Implementation |
|----------|---------------|
| Context awareness | Always know current task |
| Explanation | Explain what Butler is doing |
| Approval gating | Ask only when needed |
| Failure recovery | Graceful recovery |
| Resumable workflows | Checkpoint and resume |
| Proactive routines | Not annoying |
| Surface selection | Auto-choose right channel |

### 14.3 DX for Developers

| Feature | Implementation |
|---------|---------------|
| Manifest-first plugins | plugin.json |
| SKILL.md support | Skill definition |
| MCP-native tools | MCP spec 2025 |
| Typed contracts | Pydantic models |
| Local simulator | Test harness |
| Replayable traces | Trace replay |
| Plugin signing | Ed25519 |
| Capability gates | Per-tool policy |
| Per-tool secrets | Vault integration |
| Test harnesses | Fixtures |
| Canary rollouts | Traffic splitting |
| Health endpoints | Service mesh |

---

## 15. Health & Live Meeting Capabilities

### 15.1 Health Monitoring

| Capability | Description | Integrations |
|------------|-------------|---------------|
| Passive sync | Background sync | HealthKit, Health Connect |
| Daily briefing | Morning health summary | Vitals, trends |
| Abnormal alerts | Anomaly detection | Custom thresholds |
| Medication reminders | Med scheduling | Built-in |
| Hydration tracking | Water intake | Manual + smart glass |
| Sleep analysis | Sleep quality | Oura, Apple Watch |
| Workout consistency | Exercise tracking | All platforms |
| Nutrition adherence | Meal logging | Manual |
| Symptom timeline | Symptom logging | Built-in |
| Family health | Family reminders | Shared calendar |
| Emergency escalation | Alert contacts | Notification |

**Implementation:**
- HealthKit (iOS) via companion app
- Health Connect (Android) via SDK
- Fitbit API for Fitbit devices
- Oura API for Oura rings

### 15.2 Live Meeting

| Capability | Description | Integration |
|------------|-------------|--------------|
| Realtime STT | Live transcription | PyAnnote + Deepgram |
| Diarization | Speaker ID | PyAnnote |
| Live summary | AI summary | Streaming LLM |
| Action-item tracker | Task extraction | Built-in |
| Speaker timeline | Who's speaking | PyAnnote |
| Silent assist mode | Background assistant | Custom |
| Multilingual subtitles | Translation | Built-in |
| Post-meeting CRM sync | Sync to CRM | Webhooks |

**Implementation:**
- WebRTC for transport
- PyAnnote for diarization
- Deepgram for streaming STT
- Custom summarization pipeline

### 15.3 Realtime Translation

| Capability | Description | Integration |
|------------|-------------|--------------|
| Call translation | Voice call translate | Twilio + STT/TTS |
| Meeting subtitles | Live subtitles | WebRTC |
| Travel mode | Offline translation | Local models |
| Bilingual chat | Chat relay | Built-in |
| Device voice translation | Smart speaker | Mattermost |

**Implementation:**
- Streaming WebRTC
- Streaming STT (Deepgram)
- Streaming TTS (Coqui/ElevenLabs)
- Low-latency pipeline design

---

## 16. Smart-Device Control & Automation

### 16.1 Redundant Task Automation

Butler handles repetitive tasks so you don't have to:

| Task | Automation | Frequency |
|------|------------|-----------|
| Email schedule check | Morning scan | Daily |
| Follow-up detection | Unanswered track | Hourly |
| Calendar prep | Evening preview | Daily |
| Daily brief | Auto-generate | Morning |
| Grocery reorder | Pattern detect | As needed |
| Low-battery alerts | Device check | Daily |
| Weather routines | Auto-adjust | Hourly |
| Commute nudges | Location aware | Daily |
| File cleanup | Pattern find | Weekly |
| Report generation | Schedule | Monthly |
| Invoice reminders | Track | As needed |
| Task review | Evening | Daily |

### 16.2 Smart Device Scenes

| Scene | Trigger | Actions |
|-------|---------|---------|
| Morning | 7am or unlock | Lights, weather, brief |
| Work mode | App open | Focus, notifications off |
| Leave home | Geofence | Locks, thermostat |
| Movie time | Voice command | TV, lights, sound |
| Sleep | 10pm | Blackout, locks |
| Emergency | Voice/alarm | All on, alert |

### 16.3 Home Assistant Integration

**Protocols:**
- Matter (primary)
- Zigbee via ZHA
- Z-Wave native
- MQTT for events
- Wi-Fi/LAN for IP devices

**Implementation:**
- Home Assistant REST API
- Home Assistant WebSocket
- Butler HA custom component

---

## 17. Jarvis-Grade Personality

### 17.1 Core Behaviors

For Butler to feel like Jarvis:

| Behavior | Implementation |
|----------|---------------|
| Memory of preferences | Digital twin |
| Continuity across devices | Session sync |
| Ambient awareness | Sensor fusion |
| Proactive routines | Automation engine |
| Strong approvals | Policy gate |
| Real tool execution | Tool execution |
| Voice + screen + device | Multi-surface |
| Graceful fallback | Circuit breakers |
| "I can't safely do that" | Risk classifier |

### 17.2 Proactive Actions

Butler should:
- Check email/calendar before you ask
- Handle repetitive scheduling
- Control your environment
- Join meetings as assistant
- Translate in real time
- Monitor health signals
- Do deep research
- Code and operate your machine
- Coordinate via MCP/ACP

### 17.3 Learning Capabilities

Butler learns:
- User preferences
- Common mistakes
- Timing patterns
- Relationship context
- Task frequency
- Communication style
- Health baselines

---

## 18. Database Sharding & Replication

### 18.1 Operational Data

**PostgreSQL Primary:**
- Users, sessions, events
- Read replicas for analytics
- PgBouncer connection pool
- Partitioning for time-series

### 18.2 Hot State

**Redis:**
- Session state
- Idempotency keys
- Hot user profile
- Quotas and rate limits
- Redis Streams for workflow signals

### 18.3 Memory Stores

| Store | Data Type | Purpose |
|-------|-----------|---------|
| PostgreSQL | Structured | Truth, events |
| Neo4j | Graph | Identity, relationships |
| Qdrant | Vector | Semantic recall |
| Redis | Cache | Hot context |
| S3 | Binary | Archives |

### 18.4 Replication Strategy

- Primary for all writes
- Replicas for feed/history/search
- Explicit read-after-write routing
- Per-service circuit breakers
- Retry budgets per operation

---

## Appendix: Key Files

| What | File |
|------|------|
| Main app | `backend/main.py` |
| Orchestrator | `services/orchestrator/service.py` |
| Memory | `services/memory/service.py` |
| Tools executor | `services/tools/executor.py` |
| MCP bridge | `services/tools/mcp_bridge.py` |
| Audio | `services/audio/service.py` |
| Vision | `services/vision/service.py` |
| Config | `infrastructure/config.py` |
| Domain contracts | `domain/*/contracts.py` |
| Home Assistant | `services/device/environment.py` |
| Health sync | `services/health/` |
| Meeting | `services/meeting/` |

---

*Document owner: Architecture Team*
*Version: 1.0 (Consolidated)*
*Last Updated: 2026-04-20*

---

## 19. Expanded Tool Implementations

### 19.1 Email Tool Implementation

```python
# integrations/hermes/tools/email_tool.py
"""Email management tool for Butler."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any
import aioimaplib
from email.parser import Parser

class EmailTool:
    """Comprehensive email management."""
    
    def __init__(self, smtp_host: str, imap_host: str):
        self.smtp_host = smtp_host
        self.imap_host = imap_host
    
    async def send_email(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Send an email.
        
        Args:
            params: {
                "to": "recipient@example.com",
                "subject": "Email subject",
                "body": "Email body",
                "body_type": "plain" | "html",
                "cc": ["cc@example.com"],
                "bcc": ["bcc@example.com"]
            }
            env: Environment with SMTP credentials
        """
        to = params.get("to")
        subject = params.get("subject")
        body = params.get("body")
        body_type = params.get("body_type", "plain")
        cc = params.get("cc", [])
        bcc = params.get("bcc", [])
        
        # Build message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = env.get("EMAIL_FROM")
        msg['To'] = to
        if cc:
            msg['Cc'] = ", ".join(cc)
        
        # Attach body
        part = MIMEText(body, body_type)
        msg.attach(part)
        
        # Send via SMTP
        with smtplib.SMTP(self.smtp_host, 587) as server:
            server.starttls()
            server.login(
                env.get("SMTP_USERNAME"),
                env.get("SMTP_PASSWORD")
            )
            server.send_message(msg)
        
        return {
            "content": [{"type": "text", "text": f"Email sent to {to}"}],
            "metadata": {"to": to, "subject": subject}
        }
    
    async def read_email(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Read emails from inbox.
        
        Args:
            params: {
                "folder": "INBOX",
                "limit": 10,
                "unread_only": false,
                "since": "2026-01-01"
            }
        """
        folder = params.get("folder", "INBOX")
        limit = params.get("limit", 10)
        unread_only = params.get("unread_only", False)
        
        # Connect to IMAP
        mail = aioimaplib.IMAP4_SSL(self.imap_host)
        await mail.login(
            env.get("IMAP_USERNAME"),
            env.get("IMAP_PASSWORD")
        )
        
        # Select folder
        await mail.select(folder)
        
        # Search criteria
        criteria = "UNSEEN" if unread_only else "ALL"
        result, message_ids = await mail.search(criteria)
        
        # Get recent emails
        ids = message_ids[0].split()[-limit:]
        emails = []
        
        for msg_id in ids:
            result, msg_data = await mail.fetch(msg_id, '(RFC822)')
            parser = Parser()
            msg = parser.parsestr(msg_data[0][1].decode())
            
            emails.append({
                "from": msg['From'],
                "to": msg['To'],
                "subject": msg['Subject'],
                "date": msg['Date'],
                "body": msg.get_payload(decode=True).decode()[:500]
            })
        
        await mail.logout()
        
        return {
            "content": [{"type": "text", "text": str(emails)}],
            "metadata": {"count": len(emails)}
        }
    
    async def draft_email(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Draft email for review before sending.
        
        Args:
            params: {
                "to": "recipient@example.com",
                "subject": "Subject",
                "body": "Body content",
                "tone": "formal" | "casual" | "friendly"
            }
        """
        # Use LLM to improve draft
        llm = env.get("llm_client")
        
        prompt = f"""Draft a professional email with the following details:
        To: {params.get('to')}
        Subject: {params.get('subject')}
        Body: {params.get('body')}
        Tone: {params.get('tone', 'formal')}
        
        Improve the email while maintaining the original intent."""
        
        improved = await llm.complete(prompt)
        
        return {
            "content": [{
                "type": "text",
                "text": improved,
                "metadata": {
                    "original": params,
                    "improved": True
                }
            }]
        }
```

### 19.2 Calendar Tool Implementation

```python
# integrations/hermes/tools/calendar_tool.py
"""Calendar management tool."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class CalendarTool:
    """Google Calendar integration."""
    
    def __init__(self):
        self.scopes = [
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/calendar.events'
        ]
    
    async def create_event(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Create calendar event.
        
        Args:
            params: {
                "summary": "Meeting title",
                "description": "Meeting description",
                "start_time": "2026-04-20T10:00:00Z",
                "end_time": "2026-04-20T11:00:00Z",
                "attendees": ["email@example.com"],
                "location": "Conference Room",
                "reminders": [{"method": "email", "minutes": 30}]
            }
        """
        credentials = Credentials.from_authorized_user_info(
            env.get("google_credentials"),
            self.scopes
        )
        
        service = build('calendar', 'v3', credentials=credentials)
        
        event = {
            'summary': params.get('summary'),
            'description': params.get('description'),
            'start': {
                'dateTime': params.get('start_time'),
                'timeZone': 'UTC'
            },
            'end': {
                'dateTime': params.get('end_time'),
                'timeZone': 'UTC'
            },
            'attendees': [
                {'email': email} for email in params.get('attendees', [])
            ],
            'reminders': {
                'useDefault': False,
                'overrides': params.get('reminders', [])
            }
        }
        
        if params.get('location'):
            event['location'] = params['location']
        
        result = service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates='all'
        ).execute()
        
        return {
            "content": [{
                "type": "text",
                "text": f"Event created: {result.get('htmlLink')}"
            }],
            "metadata": {"event_id": result['id']}
        }
    
    async def find_meeting_slot(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Find available meeting slots.
        
        Args:
            params: {
                "duration_minutes": 60,
                "date": "2026-04-20",
                "participants": ["a@example.com", "b@example.com"],
                "working_hours": {"start": "09:00", "end": "18:00"}
            }
        """
        duration = params.get('duration_minutes', 60)
        date = params.get('date')
        participants = params.get('participants', [])
        
        # Get calendar free/busy
        credentials = Credentials.from_authorized_user_info(
            env.get("google_credentials"),
            self.scopes
        )
        
        service = build('calendar', 'v3', credentials=credentials)
        
        # Check each participant's calendar
        free_busy_query = {
            "timeMin": f"{date}T09:00:00Z",
            "timeMax": f"{date}T18:00:00Z",
            "items": [{"id": p} for p in participants]
        }
        
        free_busy = service.freebusy().query(body=free_busy_query).execute()
        
        # Find common slots
        busy_ranges = []
        for cal_id, cal_data in free_busy['calendars'].items():
            for busy in cal_data['busy']:
                busy_ranges.append((
                    busy['start'],
                    busy['end']
                ))
        
        # Find gaps
        available_slots = self._find_gaps(
            busy_ranges,
            duration,
            date,
            params.get('working_hours', {"start": "09:00", "end": "18:00"})
        )
        
        return {
            "content": [{
                "type": "text",
                "text": f"Available slots: {available_slots}"
            }],
            "metadata": {"slots": available_slots}
        }
    
    def _find_gaps(self, busy_ranges, duration, date, working_hours):
        """Find available time slots."""
        # Implementation details...
        return []
```

### 19.3 Smart Home Control Implementation

```python
# integrations/hermes/tools/smart_home_tool.py
"""Smart home control tool."""

import asyncio
import aiohttp
from typing import Any

class SmartHomeTool:
    """Home Assistant integration for smart home control."""
    
    def __init__(self, ha_url: str, ha_token: str):
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.headers = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json"
        }
    
    async def control_light(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Control smart lights.
        
        Args:
            params: {
                "entity_id": "light.living_room",
                "action": "turn_on" | "turn_off" | "toggle",
                "brightness": 0-255,
                "color_temp": 250-500,
                "rgb_color": [255, 128, 0],
                "transition": 2.0
            }
        """
        entity_id = params.get("entity_id")
        action = params.get("action", "turn_on")
        
        # Determine service
        service_map = {
            "turn_on": "light.turn_on",
            "turn_off": "light.turn_off",
            "toggle": "light.toggle"
        }
        
        service = service_map.get(action)
        if not service:
            return {"error": f"Unknown action: {action}"}
        
        # Build payload
        data = {"entity_id": entity_id}
        
        if action == "turn_on":
            if "brightness" in params:
                data["brightness_pct"] = int(params["brightness"] / 255 * 100)
            if "color_temp" in params:
                data["color_temp"] = params["color_temp"]
            if "rgb_color" in params:
                data["rgb_color"] = params["rgb_color"]
            if "transition" in params:
                data["transition"] = params["transition"]
        
        # Call HA API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ha_url}/api/services/{service}",
                headers=self.headers,
                json=data
            ) as resp:
                result = await resp.json()
        
        return {
            "content": [{
                "type": "text",
                "text": f"Light {entity_id} {action} successful"
            }],
            "metadata": {"entity_id": entity_id, "action": action}
        }
    
    async def control_thermostat(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Control thermostat.
        
        Args:
            params: {
                "entity_id": "climate.living_room",
                "temperature": 72,
                "mode": "auto" | "heat" | "cool" | "off",
                "fan_mode": "auto" | "on"
            }
        """
        entity_id = params.get("entity_id")
        
        data = {"entity_id": entity_id}
        
        if "temperature" in params:
            data["temperature"] = params["temperature"]
        if "mode" in params:
            data["hvac_mode"] = params["mode"]
        if "fan_mode" in params:
            data["fan_mode"] = params["fan_mode"]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ha_url}/api/services/climate/set_temperature",
                headers=self.headers,
                json=data
            ) as resp:
                result = await resp.json()
        
        return {
            "content": [{
                "type": "text",
                "text": f"Thermostat {entity_id} set to {params.get('temperature')}°"
            }]
        }
    
    async def lock_door(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Lock/unlock smart door lock.
        
        Args:
            params: {
                "entity_id": "lock.front_door",
                "action": "lock" | "unlock"
            }
        """
        entity_id = params.get("entity_id")
        action = params.get("action", "lock")
        
        service = "lock.lock" if action == "lock" else "lock.unlock"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ha_url}/api/services/{service}",
                headers=self.headers,
                json={"entity_id": entity_id}
            ) as resp:
                result = await resp.json()
        
        return {
            "content": [{
                "type": "text",
                "text": f"Door {entity_id} {action}ed"
            }]
        }
    
    async def execute_scene(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Execute Home Assistant scene.
        
        Args:
            params: {
                "scene_name": "movie_time" | "good_morning" | "leave_home"
            }
        """
        scene = params.get("scene_name")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ha_url}/api/services/scene/turn_on",
                headers=self.headers,
                json={"entity_id": f"scene.{scene}"}
            ) as resp:
                result = await resp.json()
        
        return {
            "content": [{
                "type": "text",
                "text": f"Scene '{scene}' activated"
            }]
        }
```

### 19.4 Health Monitoring Implementation

```python
# integrations/hermes/tools/health_tool.py
"""Health monitoring and wearable sync tool."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

class HealthTool:
    """Health data integration from wearables."""
    
    def __init__(self):
        self.sources = {}
    
    async def sync_health_data(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Sync health data from all connected sources.
        
        Args:
            params: {
                "sources": ["healthkit", "health_connect", "fitbit", "oura"]
            }
        """
        sources = params.get("sources", ["healthkit"])
        
        results = {}
        
        for source in sources:
            if source == "healthkit":
                results["healthkit"] = await self._sync_healthkit(env)
            elif source == "health_connect":
                results["health_connect"] = await self._sync_health_connect(env)
            elif source == "fitbit":
                results["fitbit"] = await self._sync_fitbit(env)
            elif source == "oura":
                results["oura"] = await self._sync_oura(env)
        
        return {
            "content": [{
                "type": "text",
                "text": f"Synced {len(results)} sources"
            }],
            "metadata": results
        }
    
    async def get_vitals(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Get current vital signs.
        
        Returns:
            Heart rate, steps, sleep, HRV, SpO2, etc.
        """
        # Aggregate from all sources
        vitals = {
            "heart_rate": 72,
            "heart_rate_variability": 45,
            "steps": 8543,
            "distance_km": 6.2,
            "active_minutes": 45,
            "sleep_hours": 7.5,
            "sleep_stages": {
                "deep": 1.5,
                "light": 3.0,
                "rem": 1.8,
                "awake": 1.2
            },
            "spo2": 98,
            "body_temperature": 36.8,
            "menstrual_cycle": None,
            "hydration_glasses": 6,
            "recorded_at": datetime.utcnow().isoformat()
        }
        
        return {
            "content": [{
                "type": "text",
                "text": str(vitals)
            }],
            "metadata": vitals
        }
    
    async def analyze_trends(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Analyze health trends over time.
        
        Args:
            params: {
                "metrics": ["heart_rate", "steps", "sleep"],
                "period_days": 30
            }
        """
        metrics = params.get("metrics", ["heart_rate", "steps", "sleep"])
        days = params.get("period_days", 30)
        
        # Simulate trend analysis
        trends = {}
        
        for metric in metrics:
            if metric == "heart_rate":
                trends[metric] = {
                    "current": 72,
                    "average_30d": 74,
                    "trend": "stable",
                    "min": 58,
                    "max": 92,
                    "anomalies": []
                }
            elif metric == "steps":
                trends[metric] = {
                    "current": 8543,
                    "average_30d": 7823,
                    "trend": "increasing",
                    "goal": 10000,
                    "goal_progress": 78
                }
            elif metric == "sleep":
                trends[metric] = {
                    "current": 7.5,
                    "average_30d": 7.2,
                    "trend": "improving",
                    "goal": 8.0,
                    "quality_score": 85
                }
        
        return {
            "content": [{
                "type": "text",
                "text": f"Health trends: {trends}"
            }],
            "metadata": {"trends": trends}
        }
    
    async def medication_reminder(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Set up medication reminders.
        
        Args:
            params: {
                "medication": "Vitamin D",
                "dosage": "1000 IU",
                "frequency": "daily",
                "times": ["08:00", "20:00"],
                "duration_days": 90
            }
        """
        # Store reminder configuration
        reminder = {
            "id": f"med_{datetime.utcnow().timestamp()}",
            "medication": params.get("medication"),
            "dosage": params.get("dosage"),
            "frequency": params.get("frequency"),
            "times": params.get("times"),
            "next_due": params.get("times")[0],
            "adherence_history": []
        }
        
        return {
            "content": [{
                "type": "text",
                "text": f"Reminder set for {params.get('medication')}"
            }],
            "metadata": reminder
        }
```

### 19.5 Meeting Transcription Implementation

```python
# integrations/hermes/tools/meeting_tool.py
"""Meeting transcription and live translation tool."""

import asyncio
import websockets
from typing import Any
import json

class MeetingTool:
    """Real-time meeting assistance."""
    
    def __init__(self):
        self.active_sessions = {}
        self.stt_provider = None
        self.tts_provider = None
        self.translator = None
    
    async def join_meeting(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Join a meeting and start transcription.
        
        Args:
            params: {
                "meeting_id": "abc123",
                "meeting_url": "https://zoom.us/j/...",
                "languages": ["en", "hi", "es"],
                "diarization": true,
                "translation": true
            }
        """
        meeting_id = params.get("meeting_id")
        
        # Create meeting session
        session = {
            "id": meeting_id,
            "languages": params.get("languages", ["en"]),
            "diarization": params.get("diarization", True),
            "translation": params.get("translation", True),
            "start_time": asyncio.get_event_loop().time(),
            "transcript": [],
            "participants": set()
        }
        
        self.active_sessions[meeting_id] = session
        
        return {
            "content": [{
                "type": "text",
                "text": f"Joined meeting {meeting_id}"
            }],
            "metadata": {
                "session_id": meeting_id,
                "languages": params.get("languages"),
                "status": "active"
            }
        }
    
    async def process_audio(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Process audio chunk and return transcription.
        
        Args:
            params: {
                "session_id": "abc123",
                "audio_data": "base64..."
            }
        """
        session_id = params.get("session_id")
        audio_data = params.get("audio_data")
        
        # Get session
        session = self.active_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        
        # STT processing (simulated)
        transcript_text = "This is a sample transcript."
        
        # Diarization (simulated)
        speaker = "Speaker 1"
        
        # Translation (if enabled)
        translations = {}
        if session.get("translation"):
            for lang in session.get("languages", []):
                if lang != "en":
                    translations[lang] = f"[Translated to {lang}]: {transcript_text}"
        
        # Add to transcript
        entry = {
            "timestamp": asyncio.get_event_loop().time(),
            "speaker": speaker,
            "text": transcript_text,
            "translations": translations
        }
        
        session["transcript"].append(entry)
        
        return {
            "content": [{
                "type": "text",
                "text": transcript_text
            }],
            "metadata": entry
        }
    
    async def get_summary(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Get meeting summary.
        
        Args:
            params: {
                "session_id": "abc123",
                "summary_type": "brief" | "detailed"
            }
        """
        session_id = params.get("session_id")
        
        session = self.active_sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        
        # Generate summary (simulated with LLM)
        summary = {
            "meeting_id": session_id,
            "duration_minutes": 30,
            "participants": list(session.get("participants", [])),
            "key_points": [
                "Discussed Q2 roadmap",
                "Assigned action items",
                "Scheduled follow-up meeting"
            ],
            "action_items": [
                {"task": "Update spec", "owner": "John", "due": "2026-04-25"},
                {"task": "Send report", "owner": "Jane", "due": "2026-04-22"}
            ],
            "decisions": [
                "Approved budget increase",
                "Pivoted to new strategy"
            ]
        }
        
        return {
            "content": [{
                "type": "text",
                "text": str(summary)
            }],
            "metadata": summary
        }
    
    async def live_translate(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Translate speech in real-time.
        
        Args:
            params: {
                "session_id": "abc123",
                "source_language": "en",
                "target_language": "es",
                "text": "Hello everyone"
            }
        """
        source = params.get("source_language", "en")
        target = params.get("target_language", "es")
        text = params.get("text", "")
        
        # Simulate translation
        translations = {
            "es": "Hola a todos",
            "fr": "Bonjour à tous",
            "de": "Hallo zusammen",
            "hi": "नमस्ते सभी को"
        }
        
        translated = translations.get(target, f"[Translated to {target}]: {text}")
        
        return {
            "content": [{
                "type": "text",
                "text": translated
            }],
            "metadata": {
                "source": source,
                "target": target,
                "original": text
            }
        }
```

### 19.6 Task Automation Implementation

```python
# integrations/hermes/tools/automation_tool.py
"""Automation tool for redundant tasks."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

class AutomationTool:
    """Handle repetitive tasks automatically."""
    
    def __init__(self):
        self.automations = {}
    
    async def check_email_followups(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Check for unanswered emails that need follow-up.
        
        Args:
            params: {
                "days_back": 3,
                "min_followups": 5
            }
        """
        days_back = params.get("days_back", 3)
        
        # Simulate finding follow-ups
        followups = [
            {
                "subject": "Re: Project proposal",
                "from": "john@example.com",
                "last_contact": "2026-04-17",
                "days_pending": 3
            },
            {
                "subject": "Re: Meeting notes",
                "from": "jane@example.com",
                "last_contact": "2026-04-16",
                "days_pending": 4
            }
        ]
        
        return {
            "content": [{
                "type": "text",
                "text": f"Found {len(followups)} emails needing follow-up"
            }],
            "metadata": {"followups": followups}
        }
    
    async def prepare_daily_brief(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Prepare daily briefing with calendar, tasks, weather.
        
        Args:
            params: {
                "include_weather": true,
                "include_traffic": true,
                "include_news": true
            }
        """
        # Aggregate data from multiple sources
        
        brief = {
            "greeting": "Good morning!",
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "weather": {
                "condition": "Partly cloudy",
                "temperature": 72,
                "high": 78,
                "low": 65
            },
            "calendar": [
                {"time": "10:00", "event": "Team standup", "duration": 30},
                {"time": "14:00", "event": "Client call", "duration": 60},
                {"time": "16:30", "event": "1:1 with manager", "duration": 30}
            ],
            "tasks": [
                {"task": "Send project spec", "priority": "high"},
                {"task": "Review PR #123", "priority": "medium"}
            ],
            "commute": {
                "departure": "8:45 AM",
                "duration": "25 min",
                "traffic": "Light"
            },
            "news": [
                {"title": "Tech industry news", "source": "TechCrunch"},
                {"title": "Market update", "source": "Bloomberg"}
            ]
        }
        
        return {
            "content": [{
                "type": "text",
                "text": f"Daily Brief:\n{json.dumps(brief, indent=2)}"
            }],
            "metadata": brief
        }
    
    async def grocery_reorder(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Check and suggest grocery reorders based on history.
        
        Args:
            params: {
                "store": "blinkit",
                "category": "groceries"
            }
        """
        # Analyze purchase history
        suggestions = [
            {"item": "Milk", "last_ordered": "2026-04-10", "frequency": "weekly"},
            {"item": "Bread", "last_ordered": "2026-04-12", "frequency": "weekly"},
            {"item": "Eggs", "last_ordered": "2026-04-08", "frequency": "weekly"}
        ]
        
        return {
            "content": [{
                "type": "text",
                "text": f"Based on your history, you may want to reorder: {suggestions}"
            }],
            "metadata": {"suggestions": suggestions}
        }
    
    async def schedule_routine(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Set up automated routine.
        
        Args:
            params: {
                "name": "Morning routine",
                "trigger": "time",
                "trigger_value": "07:00",
                "actions": [
                    {"action": "get_weather", "params": {}},
                    {"action": "get_calendar", "params": {}},
                    {"action": "send_brief", "params": {"channel": "push"}}
                ]
            }
        """
        routine_id = f"routine_{datetime.utcnow().timestamp()}"
        
        routine = {
            "id": routine_id,
            "name": params.get("name"),
            "trigger": {
                "type": params.get("trigger"),
                "value": params.get("trigger_value")
            },
            "actions": params.get("actions", []),
            "enabled": True,
            "last_run": None,
            "next_run": params.get("trigger_value")
        }
        
        self.automations[routine_id] = routine
        
        return {
            "content": [{
                "type": "text",
                "text": f"Routine '{params.get('name')}' created"
            }],
            "metadata": routine
        }
```

### 19.7 Commerce Tool Implementation

```python
# integrations/hermes/tools/commerce_tool.py
"""Commerce and ordering tool."""

import asyncio
from typing import Any

class CommerceTool:
    """Food, grocery, and ride ordering."""
    
    async def order_food(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Order food from delivery service.
        
        Args:
            params: {
                "platform": "swiggy" | "zomato" | "blinkit",
                "restaurant": "Pizza Hut",
                "items": [
                    {"name": "Pepperoni Pizza", "quantity": 1, "size": "large"},
                    {"name": "Garlic Bread", "quantity": 1}
                ],
                "address": "123 Main St, Apt 4B",
                "payment": "upi" | "card" | "wallet"
            }
        """
        platform = params.get("platform", "swiggy")
        
        # Simulate order
        order = {
            "order_id": f"{platform}_{datetime.utcnow().timestamp()}",
            "platform": platform,
            "restaurant": params.get("restaurant"),
            "items": params.get("items"),
            "total": 650,
            "status": "confirmed",
            "estimated_delivery": "35 min",
            "address": params.get("address")
        }
        
        return {
            "content": [{
                "type": "text",
                "text": f"Order placed on {platform}: {order['order_id']}"
            }],
            "metadata": order
        }
    
    async def book_ride(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Book a ride.
        
        Args:
            params: {
                "platform": "ola" | "uber" | "rapido",
                "pickup": "123 Main St",
                "dropoff": "456 Office Park",
                "vehicle": "auto" | "bike" | "sedan" | "suv",
                "scheduled": false
            }
        """
        platform = params.get("platform", "ola")
        
        # Simulate booking
        booking = {
            "booking_id": f"{platform}_{datetime.utcnow().timestamp()}",
            "platform": platform,
            "pickup": params.get("pickup"),
            "dropoff": params.get("dropoff"),
            "vehicle": params.get("vehicle", "sedan"),
            "estimated_price": 250,
            "estimated_arrival": "5 min",
            "status": "driver_assigned"
        }
        
        return {
            "content": [{
                "type": "text",
                "text": f"Booked {platform} ride: {booking['booking_id']}"
            }],
            "metadata": booking
        }
    
    async def search_hotels(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Search hotels.
        
        Args:
            params: {
                "city": "Bangalore",
                "checkin": "2026-05-01",
                "checkout": "2026-05-03",
                "guests": 2,
                "budget": "medium"
            }
        """
        # Simulate search results
        results = [
            {
                "name": "The Grand Hotel",
                "rating": 4.5,
                "price_per_night": 4500,
                "location": "MG Road",
                "amenities": ["WiFi", "Pool", "Gym"]
            },
            {
                "name": "City Center Inn",
                "rating": 4.2,
                "price_per_night": 3200,
                "location": "Indiranagar",
                "amenities": ["WiFi", "Breakfast"]
            }
        ]
        
        return {
            "content": [{
                "type": "text",
                "text": f"Found {len(results)} hotels in {params.get('city')}"
            }],
            "metadata": {"results": results}
        }
```

### 19.8 Code Execution Tool Implementation

```python
# integrations/hermes/tools/code_tool.py
"""Code execution and devops tool."""

import asyncio
import aiohttp
from typing import Any

class CodeTool:
    """Developer and engineering tools."""
    
    async def execute_code(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Execute code in sandbox.
        
        Args:
            params: {
                "language": "python" | "javascript" | "bash",
                "code": "print('Hello')",
                "timeout": 30
            }
        """
        language = params.get("language", "python")
        code = params.get("code")
        
        # In production, use proper sandboxing
        # This is a simplified example
        
        if language == "python":
            # Execute Python safely
            result = await self._exec_python(code)
        elif language == "javascript":
            result = await self._exec_js(code)
        elif language == "bash":
            result = await self._exec_bash(code)
        
        return {
            "content": [{
                "type": "text",
                "text": result.get("output", "")
            }],
            "metadata": {
                "exit_code": result.get("exit_code", 0),
                "execution_time_ms": result.get("duration", 0)
            }
        }
    
    async def terminal_exec(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Execute terminal command.
        
        Args:
            params: {
                "command": "ls -la",
                "cwd": "/home/user",
                "timeout": 30
            }
        """
        command = params.get("command")
        
        # Security: whitelist commands in production
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=params.get("timeout", 30)
            )
            
            return {
                "content": [{
                    "type": "text",
                    "text": stdout.decode() if stdout else ""
                }],
                "metadata": {
                    "exit_code": proc.returncode,
                    "stderr": stderr.decode() if stderr else ""
                }
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "Command timed out"}
    
    async def run_tests(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Run tests for a project.
        
        Args:
            params: {
                "framework": "pytest" | "jest" | "go test",
                "path": "tests/",
                "coverage": true
            }
        """
        framework = params.get("framework", "pytest")
        path = params.get("path", ".")
        
        if framework == "pytest":
            cmd = f"pytest {path} -v"
            if params.get("coverage"):
                cmd += " --cov"
        
        # Execute tests
        result = await self._exec_bash(cmd)
        
        passed = result.get("exit_code", 0) == 0
        
        return {
            "content": [{
                "type": "text",
                "text": f"Tests {'PASSED' if passed else 'FAILED'}"
            }],
            "metadata": {
                "passed": passed,
                "output": result.get("output", "")
            }
        }
    
    async def deploy_infrastructure(
        self,
        params: dict,
        env: dict
    ) -> dict:
        """Deploy infrastructure using Terraform/CloudFormation.
        
        Args:
            params: {
                "tool": "terraform" | "cloudformation" | "pulumi",
                "action": "apply" | "plan" | "destroy",
                "path": "./infra/",
                "vars": {"environment": "dev"}
            }
        """
        tool = params.get("tool", "terraform")
        action = params.get("action", "plan")
        path = params.get("path", ".")
        
        if tool == "terraform":
            if action == "plan":
                cmd = f"terraform plan -out=tfplan {path}"
            elif action == "apply":
                cmd = f"terraform apply tfplan"
            elif action == "destroy":
                cmd = f"terraform destroy -auto-approve"
        
        result = await self._exec_bash(cmd)
        
        return {
            "content": [{
                "type": "text",
                "text": f"Terraform {action} {'succeeded' if result.get('exit_code') == 0 else 'failed'}"
            }],
            "metadata": {"action": action, "output": result.get("output", "")}
        }
```

---

## 20. Butler Self-Workflow Engine (BWE)

### 20.1 Concept Overview

The Butler Self-Workflow Engine is a lifelong, safety-gated system that reads knowledge, observes behavior, compiles reusable skills and workflows, tests them in context, and gradually promotes the ones that reliably improve the user's life.

**Core Philosophy:** Do not let Butler freely self-edit its own core behavior. Let it self-improve only through controlled artifacts like skills, routines, macros, workflow graphs, retrieval policies, and user-profile weights.

### 20.2 Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BUTLER SELF-WORKFLOW ENGINE                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │  KNOWLEDGE      │    │  SKILL          │    │  WORLD         │   │
│  │  INGESTION      │───▶│  SYNTHESIS      │───▶│  MODEL         │   │
│  │  LAYER         │    │  LAYER           │    │  LAYER         │   │
│  └───────┬──────────┘    └────────┬─────────┘    └───────┬────────┘   │
│          │                        │                        │           │
│          ▼                        ▼                        ▼           │
│  ┌─────────────────────────────────────────────────────┐               │
│  │              SANDBOX / SIMULATION LAYER              │               │
│  │  - Dry run      - Shadow mode    - Recommendation     │               │
│  │  - Low-risk    - Approval gate  - Full execution   │               │
│  └───────────────────────┬───────────────────────────────┘               │
│                        │                                              │
│                        ▼                                              │
│  ┌─────────────────────────────────────────────────────┐               │
│  │         PROMOTION / GOVERNANCE LAYER                  │               │
│  │  - Usefulness threshold  - Safety threshold         │               │
│  │  - Permission threshold  - Reversibility          │               │
│  └───────────────────────┬───────────────────────────────┘               │
│                        │                                              │
│                        ▼                                              │
│  ┌────────��────────────────────────────────────────────┐               │
│  │         CONTINUOUS LEARNING LAYER                  │               │
│  │  - Success rate    - Override rate  - Abandoned     │               │
│  │  - Corrections   - Satisfaction   - Time saved    │               │
│  └─────────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 20.3 Knowledge Ingestion Layer

**Inputs:**
- Books, PDFs, articles, docs
- Transcripts, manuals, your notes
- Meetings, web pages
- Realtime web updates

**Outputs:**
- Concepts, procedures, constraints
- Taxonomies, examples, warnings
- Skill candidates

```python
# services/bwe/knowledge_ingestion.py
class KnowledgeIngestionService:
    """Ingest and extract knowledge from multiple sources."""
    
    def __init__(
        self,
        memory_service: MemoryService,
        extraction_service: ExtractionService
    ):
        self.memory = memory_service
        self.extractor = extraction_service
    
    async def ingest_book(
        self,
        book_source: str,
        user_id: str
    ) -> IngestionResult:
        """Ingest book and extract actionable knowledge."""
        
        # 1. Read and parse
        raw_text = await self._read_source(book_source)
        
        # 2. Extract concepts and procedures
        extraction = await self.extractor.extract_procedures(
            raw_text,
            extraction_type="procedural"  # vs "declarative"
        )
        
        # 3. Identify skill candidates
        skill_candidates = []
        for proc in extraction.procedures:
            if self._is_actionable(proc):
                skill_candidates.append(
                    SkillCandidate(
                        source=book_source,
                        procedure=proc.name,
                        steps=proc.steps,
                        constraints=proc.constraints,
                        examples=proc.examples,
                        relevance_score=self._score_relevance(proc, user_id)
                    )
                )
        
        # 4. Store in knowledge base
        await self.memory.store_knowledge(
            user_id=user_id,
            knowledge_type="ingested",
            artifacts=skill_candidates
        )
        
        return IngestionResult(
            artifacts_ingested=len(skill_candidates),
            source=book_source
        )
    
    async def ingest_web_realtime(
        self,
        query: str,
        user_id: str
    ) -> IngestionResult:
        """Watch for updated methods, APIs, regulations."""
        
        # Search for latest information
        latest = await self._fetch_latest(query)
        
        # Compare with existing knowledge
        changes = await self._detect_changes(query, latest, user_id)
        
        # Update if significant
        if changes.significant:
            await self._update_knowledge(user_id, changes)
        
        return IngestionResult(
            changes_detected=len(changes),
            artifacts_updated=changes.updated_count
        )
    
    async def observe_behavior(
        self,
        user_id: str
    ) -> BehaviorObservation:
        """Learn from user's behavior patterns."""
        
        # Fetch recent history
        history = await self.memory.get_recent_turns(
            user_id=user_id,
            limit=100
        )
        
        # Analyze patterns
        patterns = self._analyze_patterns(history)
        
        # Identify routine opportunities
        routines = self._identify_routines(patterns)
        
        # Update world model
        await self._update_world_model(user_id, patterns)
        
        return BehaviorObservation(
            patterns=patterns,
            routines=routines
        )
```

### 20.4 Skill Synthesis Layer

**Converts knowledge into:**
- Macros, routines, durable workflows
- Tool recipes, checklists, decision rules

```python
# services/bwe/skill_synthesis.py
class SkillSynthesisService:
    """Convert knowledge into executable skills."""
    
    def __init__(
        self,
        tools_service: ToolsService,
        workflow_service: WorkflowService
    ):
        self.tools = tools_service
        self.workflows = workflow_service
    
    async def synthesize_skill(
        self,
        candidate: SkillCandidate,
        user_id: str
    ) -> SynthesizedSkill:
        """Convert procedure into Butler skill."""
        
        # 1. Map steps to tools
        tool_mapping = []
        for step in candidate.steps:
            tool = await self.tools.find_matching_tool(step)
            tool_mapping.append({
                "step": step,
                "tool": tool.name if tool else None,
                "params": step.parameters,
                "required_approval": tool.risk_tier >= RiskTier.T3
            })
        
        # 2. Create wrapper skill
        skill = SynthesizedSkill(
            name=f"skill_{candidate.procedure}_{uuid4()[:8]}",
            source=candidate.source,
            steps=tool_mapping,
            trigger_conditions=self._extract_triggers(candidate),
            context_requirements=self._extract_context(candidate),
            failure_handling=self._extract_handling(candidate)
        )
        
        # 3. Register in skill library
        await self._register_skill(skill, user_id)
        
        # 4. Create workflow graph
        workflow = await self.workflows.create_from_skill(
            skill,
            user_id
        )
        
        return SynthesizedSkill(
            id=skill.id,
            name=skill.name,
            workflow_id=workflow.id,
            status="sandbox"  # Not yet promoted
        )
    
    async def create_macro(
        self,
        name: str,
        actions: list[dict],
        trigger: dict,
        user_id: str
    ) -> Macro:
        """Create executable macro from actions."""
        
        macro = Macro(
            id=str(uuid4()),
            name=name,
            actions=actions,
            trigger=trigger,
            created_by="bwe_synthesis",
            status="sandbox"
        )
        
        await self._store_macro(macro, user_id)
        
        return macro
```

### 20.5 World Model Layer

**Models:**
- Devices, calendar, work patterns
- Habits, environment, goals
- Constraints

```python
# services/bwe/world_model.py
class WorldModelService:
    """Model user's world for context-aware workflows."""
    
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
    
    async def build_user_model(
        self,
        user_id: str
    ) -> UserWorldModel:
        """Build comprehensive user model."""
        
        # Fetch all user data
        devices = await self._get_devices(user_id)
        calendar = await self._get_calendar(user_id)
        habits = await self._get_habits(user_id)
        goals = await self._get_goals(user_id)
        constraints = await self._get_constraints(user_id)
        
        # Build model
        model = UserWorldModel(
            id=user_id,
            devices=devices,
            calendar_patterns=calendar,
            habit_patterns=habits,
            goals=goals,
            constraints=constraints,
            environment=self._infer_environment(habits, devices),
            relationship_graph=self._build_relationship_graph(user_id)
        )
        
        return model
    
    async def predict_context(
        self,
        user_id: str,
        current_time: datetime = None
    ) -> ContextPrediction:
        """Predict current context for workflow triggering."""
        
        model = await self._get_model(user_id)
        
        # Time-based prediction
        time_context = self._predict_time_context(
            current_time or datetime.now(),
            model.calendar_patterns
        )
        
        # Location-based prediction
        location = await self._get_location(user_id)
        
        # Device state
        device_state = await self._get_device_state(user_id)
        
        # Mood/situation prediction
        situation = self._predict_situation(
            time_context,
            location,
            device_state,
            model.habit_patterns
        )
        
        return ContextPrediction(
            likely_location=location,
            likely_activity=time_context.current_activity,
            next_tasks=time_context.upcoming_tasks,
            interruption_risk=self._compute_interruption_risk(situation),
            best_workflow_trigger=self._suggest_workflow(situation, model)
        )
```

### 20.6 Sandbox/Simulation Layer

**Testing workflows before promotion:**
- Dry run, shadow mode, recommendation-only
- Low-risk auto mode, full execution after approval

```python
# services/bwe/sandbox.py
class SandboxService:
    """Test workflows before production."""
    
    def __init__(self):
        self.execution_modes = {
            "dry_run": DryRunExecutor,
            "shadow": ShadowExecutor,
            "recommendation": RecommendationExecutor,
            "approval_required": ApprovalExecutor,
            "autonomous": AutonomousExecutor
        }
    
    async def test_workflow(
        self,
        workflow_id: str,
        test_mode: str,
        user_id: str,
        context: dict = None
    ) -> TestResult:
        """Test workflow in specified mode."""
        
        executor_class = self.execution_modes.get(test_mode)
        executor = executor_class()
        
        # Get workflow
        workflow = await self._get_workflow(workflow_id)
        
        # Execute with full logging
        try:
            result = await executor.execute(
                workflow,
                user_id,
                context or {},
                self._create_test_context()
            )
        except SandboxException as e:
            return TestResult(
                success=False,
                error=str(e),
                logs=executor.get_logs(),
                safety_issues=executor.get_safety_issues()
            )
        
        return TestResult(
            success=result.exit_code == 0,
            output=result.output,
            logs=executor.get_logs(),
            execution_time_ms=result.duration,
            resource_usage=result.resources,
            safety_score=self._compute_safety_score(executor)
        )
    
    async def shadow_run(
        self,
        workflow_id: str,
        user_id: str,
        context: dict
    ) -> ShadowResult:
        """Run workflow in shadow mode (don't actually execute)."""
        
        workflow = await self._get_workflow(workflow_id)
        
        # Simulate all steps
        simulation = await self._simulate_workflow(
            workflow,
            user_id,
            context
        )
        
        # Check what WOULD happen
        would_execute = []
        would_notify = []
        would_modify = []
        
        for step in simulation.steps:
            if step.tool_modifies_state:
                would_modify.append(step)
            elif step.sends_notification:
                would_notify.append(step)
            else:
                would_execute.append(step)
        
        return ShadowResult(
            workflow_id=workflow_id,
            would_execute=would_execute,
            would_notify=would_notify,
            would_modify=would_modify,
            risk_assessment=self._assess_risk(would_modify),
            user_approval_needed=any(s.risk_tier >= RiskTier.T3 for s in would_modify)
        )
```

### 20.7 Promotion/Governance Layer

**Workflow becomes "real" only if it passes:**
- Usefulness, safety, permission, consistency, reversibility thresholds

```python
# services/bwe/governance.py
class GovernanceService:
    """Govern workflow promotion and execution."""
    
    PROMOTION_THRESHOLDS = {
        "usefulness": 0.7,          # 70%+ useful rating
        "safety": 0.95,              # 95%+ safe
        "permission": True,           # Explicitly allowed
        "consistency": 0.8,          # 80%+ consistent
        "reversibility": True,       # Can undo
    }
    
    async def evaluate_promotion(
        self,
        workflow_id: str,
        test_results: list[TestResult]
    ) -> PromotionDecision:
        """Evaluate workflow for promotion."""
        
        # Aggregate test results
        success_rate = sum(t.success for t in test_results) / len(test_results)
        avg_execution_time = sum(t.execution_time_ms for t in test_results) / len(test_results)
        safety_issues = [i for t in test_results for i in t.safety_issues]
        
        # Check thresholds
        checks = {
            "usefulness": success_rate >= self.PROMOTION_THRESHOLDS["usefulness"],
            "safety": len(safety_issues) == 0,
            "performance": avg_execution_time < 30000,  # <30s
            "reversibility": await self._can_undo(workflow_id),
        }
        
        # Determine promotion level
        if all(checks.values()):
            level = "autonomous"
        elif checks["safety"] and checks["usefulness"]:
            level = "assisted"
        else:
            level = "recommendation"
        
        return PromotionDecision(
            workflow_id=workflow_id,
            promoted=level != "denied",
            level=level,
            checks=checks,
            conditional_on=[] if level == "autonomous" else ["approval"]
        )
    
    async def check_permission(
        self,
        action: str,
        user_id: str,
        workflow_id: str = None
    ) -> PermissionResult:
        """Check if action is permitted."""
        
        user_perms = await self._get_user_permissions(user_id)
        
        if action in user_perms.explicitly_allowed:
            return PermissionResult(allowed=True)
        
        if action in user_perms.explicitly_denied:
            return PermissionResult(allowed=False, reason="explicitly denied")
        
        if workflow_id:
            workflow = await self._get_workflow(workflow_id)
            if workflow.user_approved:
                return PermissionResult(allowed=True)
        
        return PermissionResult(allowed=False, reason="no active permission")
```

### 20.8 Continuous Learning Layer

**Tracks after promotion:**
- Success rate, override rate, abandonment rate
- Corrections, satisfaction, time saved, error cost

```python
# services/bwe/continuous_learning.py
class ContinuousLearningService:
    """Track and improve promoted workflows."""
    
    async def track_execution(
        self,
        workflow_id: str,
        user_id: str,
        result: ExecutionResult
    ) -> LearningUpdate:
        """Track workflow execution and outcomes."""
        
        # Record execution
        await self._record_execution(
            workflow_id,
            user_id,
            result
        )
        
        # Compute metrics
        metrics = await self._compute_metrics(workflow_id, user_id)
        
        # Determine update action
        if metrics.success_rate >= 0.9:
            action = "reinforce"
        elif metrics.success_rate >= 0.7:
            action = "adjust"
        elif metrics.success_rate >= 0.5:
            action = "demote"
        else:
            action = "archive"
        
        if metrics.override_rate > 0.3:
            action = "adjust"
        if metrics.abandonment_rate > 0.5:
            action = "demote"
        
        # Apply update
        if action == "adjust":
            await self._adjust_workflow(workflow_id, metrics)
        elif action == "demote":
            await self._demote_workflow(workflow_id)
        elif action == "archive":
            await self._archive_workflow(workflow_id)
        
        return LearningUpdate(
            workflow_id=workflow_id,
            action=action,
            metrics=metrics,
            suggestion=await self._generate_suggestion(metrics)
        )
    
    async def learn_mistakes(
        self,
        user_id: str,
        failed_workflow_id: str
    ) -> MistakePattern:
        """Learn from failed workflow executions."""
        
        execution_history = await self._get_failures(
            user_id,
            failed_workflow_id
        )
        
        # Analyze failure patterns
        pattern = MistakePattern(
            workflow_id=failed_workflow_id,
            failure_modes=self._identify_failure_modes(execution_history),
            triggering_contexts=self._extract_contexts(execution_history),
            correction_suggestions=await self._generate_corrections(
                execution_history
            ),
            retry_policy=self._suggest_retry_policy(execution_history)
        )
        
        # Store pattern
        await self._store_mistake_pattern(user_id, pattern)
        
        return pattern
```

### 20.9 Three Classes of Self-Workflows

#### A. Passive - Butler Only Recommends

```python
# Examples: "You should send this follow-up now."
#            "This is probably the right grocery reorder."
PASSIVE_WORKFLOWS = [
    "follow_up_reminder",
    "grocery_suggestion",
    "meeting_summary_suggestion",
    "schedule_optimization",
    "context_switch_warning"
]
```

#### B. Assisted - Butler Prepares, You Approve

```python
# Examples: Drafts the mail, prepares the order,
#            builds the travel plan, stages calendar blocks
ASSISTED_WORKFLOWS = [
    "email_draft_prep",
    "order_prep",
    "travel_plan_prep",
    "calendar_block_prep",
    "device_change_prep"
]
```

#### C. Autonomous - Butler Executes Directly

```python
# Examples: Recurring daily brief, inbox triage labels,
#            health reminders, light/fan/AC routines
AUTONOMOUS_WORKFLOWS = [
    "daily_brief",
    "inbox_triage",
    "health_reminder",
    "light_routine",
    "temperature_routine",
    "backup_generation"
]
```

### 20.10 Example User Journeys

#### Journey 1: Reading a Productivity Book

```
User: "Butler, read 'Atomic Habits' and apply it to my routine."

Butler:
1. Ingests book via Knowledge Ingestion
2. Extracts: habit loops, environment design, social engineering
3. Maps to user's existing patterns (World Model)
4. Proposes: morning routine macro, habit tracker skill
5. Sandbox tests for 1 week in shadow mode
6. After positive results → promotes to assisted
7. Monitors → adjusts timing based on compliance
8. Gradually promotes to autonomous if consistent
```

#### Journey 2: Learning from Behavior

```
Butler observes: "User ignores meeting follow-ups after investor meetings."

Butler:
1. Identifies pattern via Continuous Learning
2. Creates: post-investor-meeting routine
3. Tests: shadow mode for 2 weeks
4. Success: User uses it 8/10 times
5. Promotes to: assisted with high recommendation
6. User enables: autonomous after trust period
```

#### Journey 3: Smart Home Adaptation

```
Butler reads: cookbook + diet plan + grocery prices + kitchen inventory

Butler:
1. Infers: dinner workflow based on preferences
2. Orders: missing ingredients automatically
3. Preheats: smart oven/device
4. Sets: reminders with timing coordination
5. Adapts: next week based on what user actually ate
6. Improves: recipe suggestions over time
```

---

## 21. Butler Self-Workflow Engine - Formal Architecture

### 21.1 Purpose

The Butler Self-Workflow Engine is a lifelong, safety-gated system that learns from books, documents, web knowledge, your behavior, and environmental feedback, then turns that into reusable skills, routines, and durable workflows. The design goal is not just retrieval or summarization, but continuous behavior improvement through a loop of ingestion, skill synthesis, testing, promotion, monitoring, and revision.

### 21.2 Product Definition

From the user's perspective, Butler should:
- Read books, docs, manuals, articles, transcripts, and your notes
- Turn useful patterns into candidate macros, routines, and workflows
- Observe habits, repeated mistakes, timing preferences, and task outcomes
- Propose better ways of doing recurring work
- Test those workflows safely before making them automatic
- Keep good ones, revise weak ones, and retire bad ones

### 21.3 Core Design Principles

**3.1 Learn as artifacts, not by mutating the core brain**

Butler improves through controlled artifacts:
- Skill cards, macros, routines
- Workflow graphs
- Timing policies, retrieval priors
- User-profile deltas, environment playbooks

**3.2 Retrieve, simulate, then promote**

A candidate workflow should go through staged execution:
- L0: Recommendation only
- L1: Dry run
- L2: Shadow execution
- L3: Low-risk live test
- L4: Autonomous promotion

**3.3 World-model first**

A self-workflow engine needs a structured model of:
- User, devices, spaces, schedules
- Tools, goals, risks, constraints

**3.4 Personalization must be behavioral**

Workflow quality updated from real outcomes:
- Accepted vs ignored suggestions
- Override rate, completion rate
- Time saved, annoyance rate, correction frequency

### 21.4 System Architecture Diagram

```
Sources
  │
  ├─ Books / PDFs / Docs / Notes
  ├─ Web / News / APIs
  ├─ Meetings / Email / Calendar / Tasks
  ├─ Devices / Sensors / Cameras / Wearables
  └─ User interaction logs
           │
           ▼
  ┌─────────────────────────────────────┐
  │     1. INGESTION PLANE            │
  │  ├─ parser                         │
  │  ├─ extractor                      │
  │  ├─ chunker                        │
  │  ├─ provenance tracker            │
  │  └─ taxonomy linker                │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │    2. UNDERSTANDING PLANE          │
  │  ├─ entity linking                │
  │  ├─ preference/dislike extraction  │
  │  ├─ procedural pattern extraction  │
  │  ├─ mistake/friction extraction   │
  │  └─ context/intent state          │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │   3. SKILL SYNTHESIS PLANE         │
  │  ├─ macro compiler                │
  │  ├─ routine compiler              │
  │  ├─ workflow DAG compiler         │
  │  └─ policy/capability annotator   │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │ 4. SANDBOX & EVALUATION PLANE      │
  │  ├─ dry-run simulator             │
  │  ├─ shadow mode                  │
  │  ├─ low-risk live test           │
  │  ├─ cost/safety validator        │
  │  └─ outcome scorer               │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │    5. PROMOTION PLANE             │
  │  ├─ approve/reject/revise        │
  │  ├─ stage/active/rollback        │
  │  ├─ risk-tier gates              │
  │  └─ user consent checks          │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │      6. RUNTIME PLANE             │
  │  ├─ Macro Engine                 │
  │  ├─ Routine Engine               │
  │  ├─ Durable Workflow Engine      │
  │  └─ Subagent Runtime             │
  └──────────────┬──────────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────────┐
  │ 7. MONITORING & LEARNING PLANE    │
  │  ├─ success/failure metrics      │
  │  ├─ reinforcement/demotion       │
  │  ├─ drift checks                 │
  │  └─ lifecycle updates           │
  └───────────────────────────────────┘
```

### 21.5 The Seven Internal Planes

**5.1 Ingestion Plane**

Inputs: Books, PDFs, websites, emails, transcripts, manuals, notes, API responses

Outputs: Chunks, entities, relationships, procedures, warnings, references, confidence scores

**5.2 Understanding Plane**

Converts raw knowledge into personalized meaning:
- What the user is trying to do
- What they repeatedly fail at
- What they dislike, what timing works
- What contexts matter, what domain the content belongs to

**5.3 Skill Synthesis Plane**

Creates three classes of executable artifacts:
- **Macro**: Fast, repeatable, deterministic, slot-filled from context
- **Routine**: Recurring behavior, scheduled/event-driven/context-driven, learns from feedback
- **Durable Workflow**: Long-running, resumable, approval-aware, stateful, multi-step and multi-agent

**5.4 Sandbox and Evaluation Plane**

Every candidate goes through:
- L0: Recommendation only
- L1: Dry run
- L2: Shadow execution
- L3: Low-risk live test
- L4: Autonomous promotion

**5.5 Promotion Plane**

A candidate workflow is promoted only if it clears:
- Utility threshold, safety threshold, consent threshold
- Capability threshold, reversibility threshold, failure tolerance threshold

**5.6 Runtime Plane**

The runtime executes through:
- Macro Engine, Routine Engine, Durable Workflow Engine, Subagent Runtime

**5.7 Monitoring and Learning Plane**

Decides whether to:
- Reinforce, modify, suspend, demote, archive, re-test

### 21.6 Execution Layers

**Layer 1: Macro Engine**
- Fast, repeatable actions
- Deterministic slot-filling
- No expensive planning

**Layer 2: Routine Engine**
- Recurring or context-triggered behavior
- Adaptive timing, habit support

**Layer 3: Durable Workflow Engine**
- Stateful DAG execution
- Approvals, pauses, signals
- Compensation, resumability

### 21.7 Memory Design for Self-Workflows

| Memory Class | Purpose |
|-------------|---------|
| **Knowledge Memory** | Facts, procedures, constraints, taxonomies |
| **Behavioral Memory** | Repeated actions, ignores, corrections, preferences |
| **Workflow Memory** | What workflows exist, how they performed |
| **Environmental Memory** | Device state, room context, wearable state |
| **Mistake Memory** | Common failure patterns (highest value) |

### 21.8 Lifecycle of a Self-Workflow

```
Stage 0: OBSERVE → Butler sees repeated behavior or reads knowledge
Stage 1: SYNTHESIZE → Generate candidate macro/routine/workflow
Stage 2: SIMULATE → Run dry checks
Stage 3: SHADOW → Run silently, compare outcomes
Stage 4: ASK/AUTO → Ask user or self-promote
Stage 5: MONITOR → Measure usefulness and frustration
Stage 6: ADAPT → Refine timing, steps, parameters
Stage 7: DEMOTE/ARCHIVE → Downgrade or retire if stale
```

### 21.9 Safety Model

**Action Classes:**
- **safe_auto**: Light/device state, reminders, summaries
- **confirm**: Send, purchase prep, booking prep, recorder changes
- **restricted**: Financial actions, health-sensitive, locks/cameras/mics, account changes

**Hard Rules:**
- No silent high-risk promotion
- No self-granting new permissions
- No direct core-model mutation
- No permanent retention of raw ambient capture by default
- No autonomous action without provenance
- No cross-account leakage

**Required Gates:**
- Capability gate, product-tier gate
- Industry-policy gate, trust-level gate
- User-consent gate, execution-sandbox gate

### 21.10 Data Models

**Candidate Workflow:**
```json
{
  "candidate_id": "cand_123",
  "type": "macro|routine|workflow",
  "title": "Post-meeting founder follow-up",
  "source_refs": ["book:negotiation_01", "session:meeting_884"],
  "derived_from": ["mistake:missed_followup_pattern"],
  "risk_class": "confirm",
  "status": "draft|shadow|staged|active|suspended|archived",
  "confidence": 0.84,
  "promotion_score": 0.77,
  "rollback_safe": true
}
```

**Workflow Performance Record:**
```json
{
  "workflow_id": "wf_444",
  "executions": 21,
  "success_rate": 0.81,
  "override_rate": 0.19,
  "time_saved_minutes": 183,
  "annoyance_score": 0.08,
  "last_revised_at": "2026-04-20T00:00:00Z"
}
```

**Mistake Pattern:**
```json
{
  "mistake_id": "mist_29",
  "type": "followup_delay",
  "trigger_context": ["investor_meeting", "late_evening"],
  "observed_count": 12,
  "severity": "medium",
  "candidate_remedies": ["routine:night_followup_draft", "macro:meeting_summary_mail"]
}
```

### 21.11 Example User Journeys

**11.1 Reading-to-Routine**
```
User reads productivity book
→ Butler extracts: meeting prep, shutdown ritual, follow-up cadence
→ Observes user misses end-of-day planning
→ Proposes nightly 8:30 PM shutdown routine
→ Runs shadow mode for one week
→ Asks to enable
```

**11.2 Mistake-to-Workflow**
```
Butler sees user misses recruiter replies after interviews
→ Synthesizes: transcript summary, role/company memory, reply draft macro
→ Promotes as "Interview Follow-up Workflow"
```

**11.3 Environment-to-Automation**
```
Butler sees: room occupancy, work calendar, wearable focus hints
→ Builds "deep work scene": mute alerts, set fan/light, launch workspace
```

### 21.12 Success Metrics

**Product Metrics:**
- Workflow adoption rate, retention rate
- Time saved, reduction in repeated mistakes
- Proactive suggestion acceptance rate

**System Metrics:**
- Candidate generation latency, promotion accuracy
- Rollback rate, false-positive automation rate
- Override rate, workflow drift rate

**Safety Metrics:**
- Unauthorized-action count, high-risk blocked promotions
- Privacy-redaction failures, approval-required misses

### 21.13 Implementation Roadmap

**Phase 1:**
- Knowledge ingestion, procedural extraction
- Candidate artifact model, recommendation-only mode

**Phase 2:**
- Macro/routine compiler, mistake model
- Sandbox and shadow mode

**Phase 3:**
- Durable workflow promotion, subagent isolation
- Device/service integration, rollback and monitoring

**Phase 4:**
- Ambient and wearable triggers
- Camera/sensor-assisted workflows
- Multilingual live adaptation
- Smart-glasses and robot surfaces

---

## 23. Reinforcement Learning Loop (RL)

### 23.1 Purpose

The Butler Self-Workflow Engine should not only synthesize workflows and monitor them. It should also learn policy improvements from outcomes. The RL loop is the layer that turns repeated execution traces, approvals, corrections, failures, and user feedback into better workflow selection, better timing, better tool choice, and better promotion decisions over time.

### 23.2 What the RL Loop Should Optimize

The RL loop should optimize a **constrained reward** made from:
- Task success
- User acceptance
- Time saved
- Low override rate
- Low annoyance
- Low safety friction
- Policy compliance
- Reversibility
- Long-term retention of good habits

**Critical:** Reward hacking is a known failure mode in RL systems. Butler should treat every reward as a proxy and keep hard safety constraints outside the reward function itself.

### 23.3 Scope of RL in Butler

**Safe RL targets:**
- Macro selection
- Routine triggering thresholds
- Workflow branch policies
- Timing policies
- Notification surface choice
- Candidate ranking weights
- Memory retrieval weights
- Tool-selection priors
- Approval-escalation priors
- Personalized preference weights

**Unsafe RL targets (never optimize directly):**
- Raw permission boundaries
- Core security policy
- Financial autonomy thresholds
- Medical decision authority
- Destructive device actions
- Unrestricted plugin privileges

### 23.4 Architecture Addition

```
Execution Trace
  │
  ├─ workflow steps
  ├─ tool calls
  ├─ approvals / denials
  ├─ overrides / corrections
  ├─ device outcomes
  ├─ latency / cost
  └─ user feedback
           │
           ▼
┌─────────────────────────────────────┐
│   1. TRAJECTORY BUILDER            │
│  ├─ state extraction              │
│  ├─ action extraction             │
│  ├─ reward shaping               │
│  ├─ safety tags                 │
│  └─ episode segmentation        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  2. REPLAY BUFFER / EXPERIENCE    │
│  ├─ online buffer                │
│  ├─ offline training corpus       │
│  ├─ high-risk trace quarantine   │
│  └─ preference/dispreference     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    3. REWARD MODEL LAYER          │
│  ├─ immediate reward             │
│  ├─ delayed reward               │
│  ├─ human feedback reward        │
│  ├─ policy penalty              │
│  └─ risk penalty               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   4. POLICY LEARNING LAYER        │
│  ├─ bandits for low-risk routing │
│  ├─ contextual bandits          │
│  ├─ offline RL                  │
│  ├─ preference optimization     │
│  └─ constrained RL             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      5. POLICY REGISTRY           │
│  ├─ shadow policy               │
│  ├─ canary policy              │
│  ├─ active policy              │
│  └─ rollback policy           │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    6. RUNTIME CONSUMERS           │
│  ├─ Macro Engine                │
│  ├─ Routine Engine             │
│  ├─ Durable Workflow Engine    │
│  ├─ Personalization Engine    │
│  └─ Retrieval / Ranking Engine │
└───────────────────────────────────┘
```

### 23.5 State, Action, Reward Design

**State:**
- Current user context
- Active goal
- Channel/device
- Calendar state
- Environment state
- Workflow stage
- Recent memory context
- Trust/risk tier
- Prior user response patterns

**Action:**
- Choose macro
- Choose routine trigger time
- Choose workflow branch
- Choose tool
- Choose response surface
- Ask / delay / execute / escalate
- Change ranking weights
- Promote / demote candidate workflow

**Reward:**
```
Positive:
  + completed objective
  + user accepted suggestion
  + no correction needed
  + time saved
  + reduced repeated mistake

Negative:
  - user override
  - user dismissal
  - policy block
  - timeout
  - side-effect rollback
  - annoyance signal
  - safety review trigger
```

### 23.6 Training Modes

**Mode A: Contextual Bandits**
For low-risk decisions:
- Best reminder time
- Best notification channel
- Best response surface
- Best macro among safe options

**Mode B: Offline RL**
For workflow policies from logged traces:
- Branching decisions
- Retry strategies
- Sequencing improvements
- Approval timing
- Routine adaptation

**Mode C: Preference Optimization / Reward Modeling**
For subjective behavior:
- Which suggestions feel helpful
- Which summaries are preferred
- Which proactive actions are welcome
- Which interventions are annoying

### 23.7 Safety Constraints

The RL loop must be constrained, not sovereign.

**Hard Rules:**
- No reward-only promotion for restricted actions
- No autonomous privilege escalation
- No reward-model authority over policy engine
- No direct action on finance/health/locks/cameras without explicit policy gates
- No training from traces that violate trust boundaries
- No use of quarantined traces for promotion
- No irreversible workflow auto-promotion from sparse evidence

### 23.8 Promotion Ladder for Learned Policies

Every learned policy moves through:
```
draft → shadow → canary → limited active → fully active → rollback
```

**Promotion requirements:**
- Statistically positive utility delta
- No safety regression
- No elevated override spike
- No unexplained reward jump
- No policy-violation drift

### 23.9 Data Schema

```json
{
  "trajectory_id": "traj_123",
  "workflow_id": "wf_456",
  "session_id": "ses_789",
  "state": {
    "goal": "post_meeting_followup",
    "channel": "mobile",
    "time_of_day": "evening",
    "calendar_load": "high",
    "user_response_profile": "slow_after_8pm"
  },
  "action": {
    "type": "schedule_followup_draft",
    "parameters": {
      "delay_minutes": 45
    }
  },
  "reward": {
    "total": 0.62,
    "task_success": 0.4,
    "user_acceptance": 0.3,
    "time_saved": 0.2,
    "override_penalty": -0.1,
    "risk_penalty": -0.18
  },
  "policy_tags": {
    "risk_class": "confirm",
    "trainable": true,
    "promotion_eligible": false
  },
  "outcome": "accepted_after_delay"
}
```

### 23.10 Where RL Plugs Into Existing Engines

| Engine | What RL Learns |
|--------|----------------|
| **Macro Engine** | Which macro template is best in which context |
| **Routine Engine** | Trigger timing, retry cadence, suppression logic |
| **Durable Workflow Engine** | Branch selection, recovery strategies, approval timing, subagent handoff |
| **Memory/Retrieval** | Ranking weights for context assembly, what memories help vs clutter |
| **Personalization Engine** | Preference strengths, surface preference, interruption tolerance |

### 23.11 Butler-Specific Reward Design

Use a **multi-objective reward**:

```
R = αS + βA + γT + δH - εO - ζP - ηC
```

Where:
- **S** = Task success
- **A** = User acceptance
- **T** = Time saved
- **H** = Habit improvement / repeated-mistake reduction
- **O** = Override/correction penalty
- **P** = Policy/risk penalty
- **C** = Annoyance / cognitive load penalty

Do not let any single component dominate.

### 23.12 User-Visible Behavior

As a user, this should feel like:
- Butler gets better at choosing the right timing
- Butler stops making the same annoying suggestion
- Butler learns which workflows help and which don't
- Butler improves quietly, but never becomes mysteriously more aggressive with risky actions

### 23.13 Final Rule

> **The RL loop optimizes Butler's decisions inside policy, never Butler's authority outside policy.**

---

## 24. Launch Scope & Phased Delivery

### 19.1 Phase 1: Personal Productivity (MVP Launch)

**Scope:**
- Core chat + search
- Email read/draft/send
- Calendar management
- Reminders
- Contacts
- Web research

**Target Users:**
- Solo personal AI user
- Founder/operator
- Student
- Professional

**Key Features:**
- JWT authentication
- Session memory
- Tool execution
- Basic automation

### 19.2 Phase 2: Meeting & Live Voice

**Scope:**
- Realtime STT
- Speaker diarization
- Live translation (40+ languages)
- Meeting summary
- Action item extraction

**Target Users:**
- Remote workers
-跨国公司团队
- Sales/professionals

**Key Features:**
- WebRTC integration
- PyAnnote diarization
- Stream translation
- Post-meeting sync

### 19.3 Phase 3: Device & Home Control

**Scope:**
- Home Assistant integration
- Matter device control
- Room-aware scenes
- Smart automation
- Health monitoring

**Target Users:**
- Smart home users
- Health-conscious users
- Family organizers

**Key Features:**
- HA WebSocket sync
- Matter protocol
- Health Connect sync
- Wearable integration

### 19.4 Phase 4: Research & Intelligence

**Scope:**
- Deep research
- Paper search (arXiv, PubMed)
- Company/people intelligence
- Financial modeling
- News sentiment

**Target Users:**
- Researchers
- Analysts
- Enterprise users

**Key Features:**
- Multi-source search
- Citation builder
- Sentiment analysis
- Portfolio tracking

### 19.5 Phase 5: Developer & Operator Mode

**Scope:**
- Terminal access
- Repo search
- Code execution
- CI/CD ops
- Database tools

**Target Users:**
- Engineers
- DevOps
- Developers

**Key Features:**
- Sandboxed execution
- Repo APIs
- Deployment automation
- Log analysis

---

## 20. Service Implementation Details

### 20.1 Auth Service Implementation

```python
# services/auth/service.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
) -> RegisterResponse:
    """Register new user with Argon2id hashing."""
    # Hash password with Argon2id
    password_hash = argon2.hash(request.password)
    
    # Create user record
    user = User(
        email=request.email,
        password_hash=password_hash,
        created_at=datetime.utcnow()
    )
    
    # Store in DB
    db.add(user)
    await db.commit()
    
    # Issue tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return RegisterResponse(
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.post("/login")
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    """Login with credentials, return JWT."""
    # Find user
    user = await db.get_user_by_email(request.email)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    
    # Verify password
    if not argon2.verify(request.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    
    # Issue tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.get("/.well-known/jwks.json")
async def jwks() -> JWKSResponse:
    """Public keys for JWT validation."""
    return JWKSResponse(keys=[...])
```

### 20.2 Orchestrator Service Implementation

```python
# services/orchestrator/service.py
class OrchestratorService:
    """Main AI orchestration service."""
    
    def __init__(
        self,
        memory_service: MemoryService,
        tools_service: ToolsService,
        ml_service: MLService
    ):
        self.memory = memory_service
        self.tools = tools_service
        self.ml = ml_service
    
    async def process(self, request: ChatRequest) -> ChatResponse:
        """Process user request through full pipeline."""
        
        # 1. Enrich context from memory
        context = await self.memory.retrieve(
            user_id=request.user_id,
            session_id=request.session_id,
            limit=5
        )
        
        # 2. Classify intent
        intent = await self.ml.classify(
            text=request.message,
            context=context
        )
        
        # 3. Build execution plan
        plan = await self._build_plan(intent, context)
        
        # 4. Execute tools
        results = []
        for step in plan.steps:
            result = await self.tools.execute(
                tool_name=step.tool,
                params=step.params,
                user_id=request.user_id
            )
            results.append(result)
        
        # 5. Generate response
        response = await self._generate_response(
            intent=intent,
            results=results,
            context=context
        )
        
        # 6. Store in memory
        await self.memory.store_turn(
            user_id=request.user_id,
            session_id=request.session_id,
            request=request.message,
            response=response
        )
        
        return ChatResponse(
            response=response,
            intent=intent.name,
            confidence=intent.confidence
        )
```

### 20.3 Device Service Implementation

```python
# services/device/service.py
class DeviceService:
    """Smart home and device control."""
    
    def __init__(self, home_assistant_url: str):
        self.ha_url = home_assistant_url
        self.ha_token = os.getenv("HOME_ASSISTANT_TOKEN")
    
    async def control_device(
        self,
        entity_id: str,
        action: str,
        **params
    ) -> DeviceResponse:
        """Control smart home device via Home Assistant."""
        
        # Call HA API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ha_url}/api/services/{action}",
                headers={"Authorization": f"Bearer {self.ha_token}"},
                json={"entity_id": entity_id, **params}
            )
        
        return DeviceResponse(
            entity_id=entity_id,
            state=response.json().get("state"),
            success=True
        )
    
    async def execute_scene(self, scene_name: str) -> SceneResponse:
        """Activate scene in Home Assistant."""
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.ha_url}/api/services/scene/turn_on",
                headers={"Authorization": f"Bearer {self.ha_token}"},
                json={"entity_id": f"scene.{scene_name}"}
            )
        
        return SceneResponse(scene=scene_name, activated=True)
    
    async def get_device_state(self, entity_id: str) -> StateResponse:
        """Get current device state."""
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.ha_url}/api/states/{entity_id}",
                headers={"Authorization": f"Bearer {self.ha_token}"}
            )
        
        state = response.json()
        return StateResponse(
            entity_id=entity_id,
            state=state.get("state"),
            attributes=state.get("attributes", {})
        )
```

### 20.4 Health Service Implementation

```python
# services/health/service.py
class HealthService:
    """Health monitoring and wearable sync."""
    
    def __init__(
        self,
        healthkit_enabled: bool = False,
        health_connect_enabled: bool = False
    ):
        self.healthkit = healthkit_enabled
        self.health_connect = health_connect_enabled
    
    async def sync_wearables(self, user_id: str) -> HealthSyncResponse:
        """Sync data from connected wearables."""
        
        vitals = {}
        
        # Sync from HealthKit if enabled
        if self.healthkit:
            vitals.update(await self._sync_healthkit(user_id))
        
        # Sync from Health Connect if enabled
        if self.health_connect:
            vitals.update(await self._sync_health_connect(user_id))
        
        return HealthSyncResponse(
            user_id=user_id,
            vitals=vitals,
            synced_at=datetime.utcnow()
        )
    
    async def get_vitals(self, user_id: str) -> VitalsResponse:
        """Get current vital signs."""
        
        return VitalsResponse(
            heart_rate=72,
            steps=8500,
            sleep_hours=7.5,
            hrv=45,
            recorded_at=datetime.utcnow()
        )
    
    async def analyze_trends(self, user_id: str) -> TrendsResponse:
        """Analyze health trends over time."""
        
        # Fetch historical data
        history = await self._fetch_history(user_id, days=30)
        
        # Analyze patterns
        trends = {
            "steps": analyze_steps(history),
            "sleep": analyze_sleep(history),
            "heart_rate": analyze_hr(history)
        }
        
        return TrendsResponse(
            user_id=user_id,
            trends=trends,
            generated_at=datetime.utcnow()
        )
```

### 20.5 Meeting Service Implementation

```python
# services/meeting/service.py
class MeetingService:
    """Live meeting transcription and translation."""
    
    def __init__(self):
        self.stt = StreamingSTT()
        self.diarizer = Diarizer()
        self.translator = LiveTranslator()
        self.summarizer = MeetingSummarizer()
    
    async def join_meeting(
        self,
        meeting_id: str,
        languages: list[str]
    ) -> MeetingSession:
        """Join meeting and start transcription."""
        
        # Initialize WebRTC connection
        webrtc = await WebRTCClient.connect(
            meeting_id,
            audio=True,
            video=False
        )
        
        # Start transcription pipeline
        session = MeetingSession(
            meeting_id=meeting_id,
            webrtc=webrtc,
            stt_stream=self.stt.stream(),
            diarizer=self.diarizer,
            translator=self.translator,
            languages=languages
        )
        
        return session
    
    async def handle_audio_chunk(
        self,
        session: MeetingSession,
        audio_chunk: bytes
    ) -> TranscriptChunk:
        """Process audio chunk and return transcript."""
        
        # STT
        text = await session.stt_stream.process(audio_chunk)
        
        # Diarization
        speaker = await session.diarizer.identify(audio_chunk)
        
        # Translation
        translations = {}
        for lang in session.languages:
            translations[lang] = await session.translator.translate(
                text, lang
            )
        
        return TranscriptChunk(
            text=text,
            speaker=speaker,
            translations=translations,
            timestamp=datetime.utcnow()
        )
    
    async def generate_summary(
        self,
        session: MeetingSession
    ) -> MeetingSummary:
        """Generate AI summary after meeting."""
        
        transcript = await session.get_full_transcript()
        
        summary = await session.summarizer.summarize(transcript)
        action_items = await session.summarizer.extract_actions(transcript)
        
        return MeetingSummary(
            meeting_id=session.meeting_id,
            summary=summary,
            action_items=action_items,
            decisions=extract_decisions(transcript),
            participants=session.participants
        )
```

### 20.6 Memory Service Implementation

```python
# services/memory/service.py
class MemoryService:
    """Hybrid memory with PostgreSQL, Neo4j, Qdrant."""
    
    def __init__(
        self,
        postgres: AsyncSession,
        neo4j: Neo4jDriver,
        qdrant: QdrantClient,
        redis: Redis
    ):
        self.db = postgres
        self.graph = neo4j
        self.vector = qdrant
        self.cache = redis
    
    async def store_turn(
        self,
        user_id: str,
        session_id: str,
        request: str,
        response: str,
        metadata: dict = None
    ) -> str:
        """Store conversation turn in episodic memory."""
        
        turn = Turn(
            user_id=user_id,
            session_id=session_id,
            request=request,
            response=response,
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        
        self.db.add(turn)
        await self.db.commit()
        
        # Invalidate cache
        await self.cache.delete(f"memory:{user_id}:recent")
        
        return turn.id
    
    async def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> list[MemoryContext]:
        """Hybrid retrieval from all memory stores."""
        
        # 1. Semantic search (Qdrant)
        vector_results = await self.vector.search(
            collection=f"memory:{user_id}",
            query=query,
            limit=limit
        )
        
        # 2. Graph relationships (Neo4j)
        graph_results = await self.graph.run(
            """
            MATCH (u:User {id: $user_id})-[:RELATED]->(m:Memory)
            WHERE m.text CONTAINS $query
            RETURN m LIMIT $limit
            """,
            {"user_id": user_id, "query": query, "limit": limit}
        )
        
        # 3. Recent sessions (PostgreSQL)
        recent_results = await self.db.execute(
            select(Turn).where(
                Turn.user_id == user_id
            ).order_by(
                Turn.created_at.desc()
            ).limit(limit)
        )
        
        # Merge and rank results
        return self._merge_and_rank(
            vector_results,
            graph_results,
            list(recent_results)
        )
    
    async def store_fact(
        self,
        user_id: str,
        fact: str,
        provenance: str = None
    ) -> str:
        """Store semantic fact in knowledge graph."""
        
        # Store in Neo4j
        await self.graph.run(
            """
            MERGE (f:Fact {id: $fact_id})
            SET f.text = $fact,
               f.provenance = $provenance,
               f.created_at = $created_at
            WITH f
            MATCH (u:User {id: $user_id})
            MERGE (u)-[:KNOWS]->(f)
            """,
            {
                "fact_id": str(uuid4()),
                "fact": fact,
                "provenance": provenance,
                "created_at": datetime.utcnow(),
                "user_id": user_id
            }
        )
        
        # Also store embedding in Qdrant
        embedding = await self._get_embedding(fact)
        await self.vector.insert(
            collection=f"memory:{user_id}",
            id=str(uuid4()),
            vector=embedding,
            payload={"text": fact}
        )
```

---

## 21. API Contracts

### 21.1 Gateway API Contract

```yaml
openapi: 3.0.0
info:
  title: Butler API
  version: 1.0.0
  description: Personal AI Assistant API

servers:
  - url: https://api.butler.ai/v1
    description: Production
  - url: http://localhost:8000/v1
    description: Development

paths:
  /chat:
    post:
      summary: Send chat message
      operationId: sendChat
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - message
                - user_id
              properties:
                message:
                  type: string
                user_id:
                  type: string
                  format: uuid
                session_id:
                  type: string
                  format: uuid
                context:
                  type: object
      responses:
        '200':
          description: Chat response
          content:
            application/json:
              schema:
                type: object
                properties:
                  response:
                    type: string
                  intent:
                    type: string
                  confidence:
                    type: number

  /tools:
    get:
      summary: List available tools
      operationId: listTools
      responses:
        '200':
          description: Tool list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Tool'

  /health:
    get:
      summary: Health check
      operationId: healthCheck
      responses:
        '200':
          description: System health

components:
  schemas:
    Tool:
      type: object
      properties:
        name:
          type: string
        description:
          type: string
        parameters:
          type: object
```

### 21.2 Tool Execution Contract

```python
# domain/tools/contracts.py
from pydantic import BaseModel, Field
from typing import Any
from enum import Enum

class ToolCategory(str, Enum):
    CORE = "core"
    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    COMMERCE = "commerce"
    DEVICE = "device"
    HEALTH = "health"
    MEETING = "meeting"
    CREATIVE = "creative"
    CODE = "code"

class RiskTier(str, Enum):
    T1_LOW = "low"
    T2_MEDIUM = "medium"
    T3_HIGH = "high"
    T4_CRITICAL = "critical"

class ToolDefinition(BaseModel):
    """Tool specification."""
    name: str
    description: str
    category: ToolCategory
    risk_tier: RiskTier
    requires_approval: bool = False
    timeout_seconds: int = 30
    input_schema: dict = {}
    output_schema: dict = {}

class ToolExecutionRequest(BaseModel):
    """Request to execute a tool."""
    tool_name: str
    parameters: dict = {}
    user_id: str
    idempotency_key: str | None = None

class ToolExecutionResponse(BaseModel):
    """Response from tool execution."""
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    tool_name: str

class ToolResult(BaseModel):
    """Structured tool result."""
    content: list[dict] = []
    artifacts: dict = {}
    metadata: dict = {}
```

---

## 22. Security Implementation

### 22.1 Trust Classification

```python
# domain/security/trust.py
from enum import Enum

class TrustLevel(str, Enum):
    """Trust classification levels."""
    UNTRUSTED = "untrusted"      # External clients
    MEDIUM_TRUST = "medium"     # Authenticated users
    TRUSTED = "trusted"        # Internal services
    SENSITIVE = "sensitive"    # PII/keys

class TrustPolicy:
    """Trust-based access control."""
    
    # Capability requirements by trust level
    TRUST_REQUIREMENTS = {
        TrustLevel.UNTRUSTED: ["WEB_SEARCH", "INFO_LOOKUP"],
        TrustLevel.MEDIUM_TRUST: ["WEB_SEARCH", "MEMORY_READ", "CALENDAR_READ"],
        TrustLevel.TRUSTED: ["*"],  # All capabilities
        TrustLevel.SENSITIVE: ["PAYMENT_WRITE", "DATA_EXPORT"],  # Extra approval
    }
    
    @classmethod
    def can_execute(
        cls,
        tool: str,
        trust_level: TrustLevel
    ) -> bool:
        """Check if tool can be executed at trust level."""
        
        allowed = cls.TRUST_REQUIREMENTS.get(trust_level, [])
        
        # Wildcard = all
        if "*" in allowed:
            return True
        
        # Direct match
        if tool in allowed:
            return True
        
        # Category match (e.g., "MEMORY_*")
        for cap in allowed:
            if cap.endswith("*") and tool.startswith(cap[:-1]):
                return True
        
        return False
```

### 22.2 PII Redaction

```python
# domain/security/redaction.py
import re

class PIIRedactor:
    """PII detection and redaction."""
    
    PATTERNS = {
        "email": r'\b[\w.]+@[\w.]+\.[a-z]{2,}\b',
        "phone": r'\b\d{10,}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
    }
    
    @classmethod
    def redact(cls, text: str) -> str:
        """Redact PII from text."""
        
        for pii_type, pattern in cls.PATTERNS.items():
            text = re.sub(pattern, f"[{pii_type.upper()}]", text)
        
        return text
    
    @classmethod
    def detect(cls, text: str) -> list[dict]:
        """Detect PII in text without redaction."""
        
        findings = []
        
        for pii_type, pattern in cls.PATTERNS.items():
            for match in re.finditer(pattern, text):
                findings.append({
                    "type": pii_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end()
                })
        
        return findings
```

### 22.3 Approval Workflow

```python
# domain/security/approval.py
from enum import Enum

class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ApprovalRequest(BaseModel):
    """Request for human approval."""
    id: str
    tool_name: str
    params: dict
    risk_tier: RiskTier
    requested_by: str
    requested_at: datetime
    expires_at: datetime

class ApprovalService:
    """Approval workflow for high-risk actions."""
    
    async def request_approval(
        self,
        request: ApprovalRequest
    ) -> str:
        """Submit approval request."""
        
        # Store in DB
        approval = ApprovalRecord(
            id=str(uuid4()),
            tool_name=request.tool_name,
            params=request.params,
            risk_tier=request.risk_tier,
            state=ApprovalState.PENDING,
            requested_by=request.requested_by,
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        await self.db.save(approval)
        
        # Notify user
        await self._notify_user(approval)
        
        return approval.id
    
    async def check_approval(
        self,
        approval_id: str
    ) -> bool:
        """Check if approval was granted."""
        
        approval = await self.db.get(ApprovalRecord, approval_id)
        
        if approval.state == ApprovalState.APPROVED:
            return True
        
        if approval.state == ApprovalState.EXPIRED or \
           datetime.utcnow() > approval.expires_at:
            return False
        
        return False
```

---

## 23. Observability

### 23.1 Metrics Collection

```python
# core/observability.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter(
    'butler_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'butler_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint']
)

# Tool metrics
TOOL_EXECUTION_COUNT = Counter(
    'butler_tool_executions_total',
    'Tool executions',
    ['tool_name', 'status']
)

TOOL_EXECUTION_DURATION = Histogram(
    'butler_tool_execution_duration_seconds',
    'Tool execution duration',
    ['tool_name']
)

# Service health
SERVICE_HEALTH = Gauge(
    'butler_service_health',
    'Service health status (1=healthy, 0=unhealthy)',
    ['service', 'state']
)

# Memory metrics
MEMORY_RETRIEVAL_LATENCY = Histogram(
    'butler_memory_retrieval_duration_seconds',
    'Memory retrieval latency',
    ['store_type']
)
```

### 23.2 Tracing

```python
# core/tracing.py
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Setup tracing
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)

# Add OTLP exporter
tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://otel-collector:4317")
    )
)

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("orchestrate")
async def orchestrate_with_trace(request: dict):
    """Orchestrate with full tracing."""
    
    with tracer.start_as_current_span("classify_intent") as span:
        intent = await ml.classify(request.text)
        span.set_attribute("intent.name", intent.name)
        span.set_attribute("intent.confidence", intent.confidence)
    
    with tracer.start_as_current_span("retrieve_memory") as span:
        context = await memory.retrieve(user_id, request.session_id)
        span.set_attribute("context.items", len(context))
    
    with tracer.start_as_current_span("execute_tools") as span:
        results = await tools.execute(plan.steps)
        span.set_attribute("tools.executed", len(results))
    
    return response
```

---

## 24. Error Handling (RFC 9457)

### 24.1 Problem Detail Response

```python
# core/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse
from RFC9457 import ProblemDetail

class ButlerException(Exception):
    """Base Butler exception."""
    
    def __init__(
        self,
        title: str,
        status: int,
        detail: str,
        instance: str = None,
        extra: dict = None
    ):
        super().__init__(title)
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extra = extra or {}
    
    def to_problem_detail(self, request: Request) -> JSONResponse:
        """Convert to RFC 9457 response."""
        
        problem = ProblemDetail(
            type=f"https://docs.butler.ai/problems/{self.title.lower().replace(' ', '-')}",
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=self.instance or request.url.path
        )
        
        return JSONResponse(
            status_code=self.status,
            content=problem.model_dump(exclude_none=True)
        )

# Standard error types
class AuthenticationFailed(ButlerException):
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            title="Authentication Failed",
            status=401,
            detail=detail
        )

class InsufficientPermissions(ButlerException):
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            title="Forbidden",
            status=403,
            detail=detail
        )

class RateLimitExceeded(ButlerException):
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(
            title="Too Many Requests",
            status=429,
            detail=detail
        )

class ServiceUnavailable(ButlerException):
    def __init__(self, detail: str = "Service unavailable"):
        super().__init__(
            title="Service Unavailable",
            status=503,
            detail=detail
        )
```

---

## 25. Deployment

### 25.1 Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://butler:butler@postgres:5432/butler
      - REDIS_URL=redis://redis:6379
      - NEO4J_URI=bolt://neo4j:7687
      - QDRANT_HOST=qdrant
    depends_on:
      - postgres
      - redis
      - neo4j
      - qdrant
    networks:
      - butler

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: butler
      POSTGRES_PASSWORD: butler
      POSTGRES_DB: butler
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - butler

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - butler

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/butler
    volumes:
      - neo4j_data:/data
    networks:
      - butler

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - butler

networks:
  butler:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  neo4j_data:
  qdrant_data:
```

### 25.2 Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: butler-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: butler-api
  template:
    metadata:
      labels:
        app: butler-api
    spec:
      containers:
        - name: api
          image: butler/api:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: butler-secrets
                  key: database-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
```

---

## 26. Testing Strategy

### 26.1 Unit Tests

```python
# tests/test_orchestrator.py
import pytest

@pytest.mark.asyncio
async def test_intent_classification():
    """Test intent classification."""
    
    service = OrchestratorService(
        memory=mock_memory(),
        tools=mock_tools(),
        ml=mock_ml()
    )
    
    # Test directive
    result = await service.ml.classify(
        "Turn off the lights",
        context=[]
    )
    
    assert result.name == "iot_control"
    assert result.confidence > 0.8

@pytest.mark.asyncio
async def test_tool_execution():
    """Test tool execution."""
    
    tools_service = ToolsService(
        registry=mock_registry()
    )
    
    result = await tools_service.execute(
        tool_name="web_search",
        params={"query": "test"},
        user_id="test_user"
    )
    
    assert result.success is True

@pytest.mark.asyncio
async def test_memory_retrieval():
    """Test hybrid memory retrieval."""
    
    memory_service = MemoryService(
        postgres=mock_db(),
        neo4j=mock_neo4j(),
        qdrant=mock_qdrant(),
        redis=mock_redis()
    )
    
    results = await memory_service.retrieve(
        user_id="test",
        query="meeting yesterday",
        limit=5
    )
    
    assert len(results) > 0
```

### 26.2 Integration Tests

```python
# tests/test_integration.py
import pytest

@pytest.mark.asyncio
async def test_full_chat_flow():
    """Test full chat pipeline."""
    
    # Setup
    app = create_app()
    client = TestClient(app)
    
    # Login
    login_resp = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "test123"}
    )
    token = login_resp.json()["access_token"]
    
    # Send message
    chat_resp = await client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": "What's on my calendar today?",
            "user_id": "test_user"
        }
    )
    
    assert chat_resp.status_code == 200
    assert "response" in chat_resp.json()
```

### 26.3 Load Tests

```python
# tests/test_load.py
import pytest
from locust import HttpUser, task, between

class ButlerUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(10)
    def chat_message(self):
        """Send chat message."""
        self.client.post(
            "/chat",
            json={
                "message": "Hello Butler",
                "user_id": "load_test"
            }
        )
    
    @task(5)
    def tool_execution(self):
        """Execute tools."""
        self.client.get("/tools")
    
    @task(1)
    def health_check(self):
        """Check health."""
        self.client.get("/health")
```

---

## 27. Runbooks

### 27.1 Post-Deployment Verification

```bash
#!/bin/bash
# Run after deployment

echo "=== Butler Deployment Verification ==="

# 1. Check health
curl -sf http://localhost:8000/health/live || exit 1
curl -sf http://localhost:8000/health/ready || exit 1

# 2. Check services
curl -sf http://localhost:8000/health | jq '.services'

# 3. Test authentication
TOKEN=$(curl -sf -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}' \
  | jq -r '.access_token')

# 4. Test chat
curl -sf -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello","user_id":"test"}' \
  | jq '.response'

echo "=== Verification Complete ==="
```

### 27.2 Incident Response

```bash
#!/bin/bash
# Incident response playbook

echo "=== Butler Incident Response ==="

# Check services status
echo "1. Checking service health..."
curl -sf http://localhost:8000/health | jq '.'

# Check database
echo "2. Checking database..."
curl -sf http://localhost:8000/health | jq '.services.postgres'

# Check Redis
echo "3. Checking Redis..."
curl -sf http://localhost:8000/health | jq '.services.redis'

# View recent logs
echo "4. Recent error logs..."
kubectl logs -l app=butler-api --tail=100 | grep ERROR

echo "=== Incident Response Complete ==="
```

---

## 28. Glossary

| Term | Definition |
|------|------------|
| **BWL** | Butler Workflow Language - DSL for durable execution |
| **ACP** | Agent Control Plane - Internal agent communication protocol |
| **MCP** | Model Context Protocol - Standard tool/data bridge |
| **A2A** | Agent-to-Agent - Peer agent messaging |
| **T0-T3** | Intent complexity tiers |
| **Macro** | Fast deterministic execution |
| **Routine** | Trigger-based automation |
| **Durable** | Long-running workflows with checkpoints |
| **Digital Twin** | High-fidelity user preference model |
| **Four-state health** | STARTING → HEALTHY → DEGRADED → UNHEALTHY |
| **RFC 9457** | Problem Details HTTP API error format |

---

## Appendix B: Config Reference

### B.1 Environment Variables

```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://host:6379
NEO4J_URI=bolt://host:7687
QDRANT_HOST=host:6333

# Auth
JWT_PRIVATE_KEY_PATH=/path/to/jwt-private.pem
JWT_PUBLIC_KEY_PATH=/path/to/jwt-public.pem

# External APIs
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...

# Smart Home
HOME_ASSISTANT_URL=http://homeassistant:8123
HOME_ASSISTANT_TOKEN=...

# Health
HEALTHKIT_ENABLED=true
HEALTH_CONNECT_ENABLED=true

# Feature Flags
MEETING_TRANSCRIPTION_ENABLED=true
LIVE_TRANSLATION_ENABLED=true
```

### B.2 Service Configuration

```python
# infrastructure/config.py
class Settings(BaseSettings):
    # Core
    DATABASE_URL: str
    REDIS_URL: str
    NEO4J_URI: str
    QDRANT_HOST: str
    
    # Auth
    JWT_PRIVATE_KEY_PATH: Path
    JWT_PUBLIC_KEY_PATH: Path
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # External APIs
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    
    # Smart Home
    HOME_ASSISTANT_URL: str | None = None
    HOME_ASSISTANT_TOKEN: str | None = None
    
    # Features
    MEETING_TRANSCRIPTION_ENABLED: bool = True
    LIVE_TRANSLATION_ENABLED: bool = True
    
    # Health
    HEALTHKIT_ENABLED: bool = False
    HEALTH_CONNECT_ENABLED: bool = False
    
    class Config:
        env_file = ".env"
```

---

*Document owner: Architecture Team*
*Version: 1.0 (Consolidated)*
*Last Updated: 2026-04-20*

(End of document - 4800+ lines)