# Butler Super Agent Build Plan

> **Status:** Implementation Blueprint  
> **Created:** 2026-04-20  
> **Target:** All 18 capability areas across Mac + cloud + mobile

---

## Executive Summary

Butler already has **substantial infrastructure** for all 18 capability areas. This plan identifies:
- What exists and can be reused
- What's missing and needs to be added
- Implementation order and dependencies

**Conclusion:** ~80% of architecture exists, need ~20% integration and model deployments.

---

## Part 1: Existing Reusable Code Inventory

### 1.1 Core Services (18 services)

| Service | Status | Key Files | LOC | Reusable For |
|---------|--------|----------|-----|-------------|
| **gateway** | ✅ Working | operator_plane.py, session_manager.py, rate_limiter.py | 800 | API layer, streaming, rate limiting |
| **auth** | ✅ Working | service.py (34KB), jwt.py, credential_pool.py | 600 | JWT, OIDC, passkeys |
| **orchestrator** | ✅ Working | service.py (17KB), executor.py, blender.py | 700 | Task execution, planning, subagents |
| **memory** | ✅ Working | service.py, retrieval.py, digital_twin.py | 1200 | Vector + graph + episodic memory |
| **ml** | ✅ Working | runtime.py, personalization_engine.py, smart_router.py | 900 | ML routing, embeddings, intent |
| **tools** | ✅ Working | executor.py (20KB), mcp_bridge.py, skill_marketplace.py | 900 | Tool execution, MCP, skills |
| **search** | ✅ Working | service.py, answering_engine.py, deep_research.py | 600 | Web search, research, QA |
| **communication** | ✅ Working | channel_registry.py (18KB), delivery.py | 700 | Multi-channel messaging |
| **realtime** | ✅ Working | listener.py, ws_mux.py, stream_dispatcher.py | 500 | WebSockets, events, presence |
| **device** | ✅ Working | environment.py, adapters.py, capabilities.py | 400 | Device awareness, Home Assistant |
| **security** | ✅ Working | policy.py, safety.py, trust.py | 300 | Policy engine, redaction |
| **vision** | ⚠️ Stub | service.py, models.py (14KB) | 200 | Image understanding |
| **audio** | ✅ Working | service.py, stt.py, tts.py, diarization.py | 500 | STT, TTS, diarization |
| **workflow** | ✅ Working | engine.py, acp_server.py | 200 | Workflow automation |
| **calendar** | ⚠️ Stub | service.py | 50 | Scheduling |
| **meetings** | ⚠️ Stub | service.py | 50 | Meeting coordination |
| **cron** | ✅ Working | cron_service.py | 100 | Scheduled jobs |
| **plugin_ops** | ✅ Working | clawhub_client.py, lifecycle_manager.py | 200 | Plugin lifecycle |

**Total:** ~10,000 lines of working Python code

---

### 1.2 Domain Contracts

| Domain | Files | Purpose |
|--------|-------|---------|
| `domain/orchestrator/` | runtime_kernel.py (9KB), workflow_dag.py, state.py | Execution contracts |
| `domain/memory/` | contracts.py, session_store.py, write_policy.py | Memory contracts |
| `domain/tools/` | butler_tool_registry.py (9KB), hermes_compiler.py (17KB) | Tool contracts |
| `domain/plugins/` | plugin_bus.py (9KB), mercury_runtime.py | Plugin system |
| `domain/auth/` | contracts.py, models.py | Auth contracts |
| `domain/events/` | normalizer.py (13KB), schemas.py | Event models |
| `domain/gateway/` | platform_registry.py | Platform definitions |

---

### 1.3 Infrastructure

| Component | Location | What It Provides |
|-----------|----------|-----------------|
| **Database** | `infrastructure/database.py` | PostgreSQL + SQLAlchemy |
| **Cache** | `infrastructure/cache.py` | Redis |
| **Graph Store** | `infrastructure/memory/neo4j_client.py` | Neo4j |
| **Vector Store** | `infrastructure/memory/qdrant_client.py` | Qdrant |
| **Config** | `infrastructure/config.py` | Settings |
| **Observability** | `core/observability.py` | Telemetry, health |

---

### 1.4 API Routes

| Route | Files | Endpoints |
|-------|-------|----------|
| `api/routes/gateway/` | gateway.py | /chat, /chat/stream, /chat/history |
| `api/routes/auth/` | auth.py | /login, /register, /token |
| `api/routes/memory/` | memory.py | /memory, /memory/search |
| `api/routes/tools/` | tools.py | /tools, /tools/execute |
| `api/routes/search/` | search.py | /search, /research |
| `api/routes/realtime/` | realtime.py | WS /ws, /events |
| `api/routes/mcp/` | mcp.py | MCP bridge, manifest |
| `api/routes/audio/` | audio.py | STT/TTS endpoints |
| `api/routes/device/` | device.py | Device control |

---

### 1.5 Mobile App

| Component | Location | Status |
|-----------|----------|--------|
| React Native (Expo) | `app/` | Basic scaffolding |

---

## Part 2: Capability Gap Analysis

### 2.1 Launch Now Capabilities (Already Have ✅)

| Capability | Existing Service | What Needs Work |
|------------|-----------------|-----------------|
| Core chat + planning | `orchestrator` | Already working |
| Web research | `search` + `deep_research` | Add more providers |
| Memory + personalization | `memory` + `ml` | Add more sources |
| Reminders/calendar | `calendar` | Connect Google/MS |
| Coding + terminal | `tools` + `orchestrator` | Add computer-use |
| Weather | `search` web provider | Already works via search |
| Finance watchlists | `search` + `ml` features | Add Alpha Vantage |
| STT/TTS | `audio` service | Add more providers |
| Push notifications | `realtime` | Connect FCM/APNs |
| MCP tool federation | `tools` + `mcp_bridge` | Already working |

---

### 2.2 Launch Right After Capabilities

| Capability | Existing Service | What to Build |
|------------|-----------------|---------------|
| Food/grocery ordering | `communication` | Add Swiggy/Zomato/ONDC |
| Ride booking | `device` + `communication` | Add Uber/Ola APIs |
| Call assistant | `audio` | Add Twilio Voice |
| Smart-home control | `device` environment | Connect more Matter devices |
| Camera/vision | `vision` service | Add Grounding DINO/SAM |
| Health context | `device` | Add Health Connect |

---

### 2.3 Launch Later Capabilities

| Capability | What to Build |
|------------|---------------|
| Robotics/embodiment | ROS 2 + Nav2 + MoveIt 2 |
| Smart glasses | Visual AI + AR display |
| Full ambient Butler | All above + presence |

---

## Part 3: Implementation Order

### Phase 1: Core Polish (Week 1-2)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 1.1 Fix orchestrator subagent runtime | `orchestrator` | Add timeout handling |
| 1.2 Enhance memory retrieval | `memory` | Better reranking |
| 1.3 Add Alpha Vantage to search | `search` | Stock data provider |
| 1.4 Connect calendar to Google | `calendar` | Google Calendar API |
| 1.5 Add computer-use tool | `tools` | Playwright browser tool |

### Phase 2: Voice + Communication (Week 3-4)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 2.1 Add Twilio voice | `audio` | Voice calling |
| 2.2 Add faster-whisper | `audio` | Local STT |
| 2.3 Add Coqui TTS | `audio` | Local TTS |
| 2.4 Connect FCM | `realtime` | Push notifications |
| 2.5 Add WhatsApp channel | `communication` | WhatsApp Business API |

### Phase 3: Commerce + Mobility (Week 5-6)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 3.1 Add Swiggy API | `communication` | Food ordering |
| 3.2 Add ONDC adapter | `communication` | Open network |
| 3.3 Add Uber API | `device` | Ride booking |
| 3.4 Add Ola Maps | `device` | Maps/geocoding |

### Phase 4: Smart Home + Health (Week 7-8)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 4.1 Enhance Home Assistant | `device` | More device types |
| 4.2 Add Matter support | `device` | Matter protocol |
| 4.3 Add Health Connect | `device` | Wearable data |
| 4.4 Add Android companion | `app/` | Android companion |

### Phase 5: Vision + Advanced (Week 9-12)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 5.1 Add Grounding DINO | `vision` | Object detection |
| 5.2 Add SAM 3 | `vision` | Segmentation |
| 5.3 Add OCR pipeline | `vision` | Document OCR |
| 5.4 Enhance mobile app | `app/` | Full companion |

### Phase 6: Robotics (Month 4+)

| Task | Existing to Use | New to Add |
|------|----------------|-----------|
| 6.1 Add ROS 2 bridge | `workflow` | ROS 2 integration |
| 6.2 Add Nav2 | `workflow` | Navigation |
| 6.3 Add MoveIt 2 | `workflow` | Manipulation |

---

## Part 4: Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        BUTLER SUPER AGENT                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │   GATEWAY  │  │    AUTH    │  │ ORCHESTRATOR│                │
│  │    API     │  │    JWT    │  │  Executor   │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                │
│         │               │               │                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    TOOL EXECUTION LANES                  │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │    │
│  │  │   API   │ │   MCP   │ │BROWSER   │ │ DEVICE  │     │    │
│  │  │  Lane   │ │  Lane   │ │  Lane   │ │  Lane   │     │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    MEMORY STACK                    │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐  │    │
│  │  │Postgres│ │ Redis  │ │ Qdrant │ │Neo4j │  │    │
│  │  │Hot    │ │Cache   │ │Vector  │ │Graph │  │    │
│  │  └────────┘ └────────┘ └────────┘ └──────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                               │
│  ┌─────────────────────────────────���─���─────────────────────┐    │
│  │                   CAPABILITY SERVICES                   │    │
│  │  ┌─────┐ ┌──────┐ ┌───────┐ ┌──────┐ ┌───────┐       │    │
│  │  │Audio│ │Vision│ │Search │ │Comm  │ │Device│       │    │
│  │  │     │ │      │ │       │ │      │ │      │       │    │
│  │  │STT  │ │DINO  │ │Alpha  │ │Twilio│ │HomeKit       │    │
│  │  │TTS  │ │SAM 3 │ │Vantage│ │ONDC  │ │Matter       │    │
│  │  └─────┘ └──────┘ └───────┘ └──────┘ └───────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                      ML RUNTIME                       │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐       │    │
│  │  │  Fast LLM   │ │ Embeddings │ │  Reranker   │       │    │
│  │  │  (local)   │ │ (local)    │ │ (cloud)     │       │    │
│  │  └────────────┘ └────────────┘ └────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 5: External Dependencies

### Already Integrated

| Service | Purpose | Integration |
|---------|---------|--------------|
| PostgreSQL | Primary database | SQLAlchemy |
| Redis | Cache + pub/sub | aioredis |
| Neo4j | Graph memory | neo4j driver |
| Qdrant | Vector search | qdrant-client |
| FastAPI | HTTP server | starlette |
| Claude/OpenAI | LLM providers | HTTP API |
| Twilio | SMS/calls | twilio SDK |
| Home Assistant | Smart home | REST + WebSocket |

### Need to Add

| Service | Purpose | Priority | Estimated Effort |
|--------|---------|----------|-----------------|
| **faster-whisper** | Local STT | High | 1 day |
| **Coqui TTS** | Local TTS | High | 1 day |
| **Alpha Vantage** | Finance data | Medium | 2 days |
| **Grounding DINO** | Object detection | Medium | 3 days |
| **SAM 3** | Segmentation | Medium | 3 days |
| **Google Calendar** | Scheduling | Medium | 2 days |
| **Google Tasks** | Todos | Low | 2 days |
| **Swiggy API** | Food ordering | Medium | 3 days |
| **ONDC** | Open network | Medium | 5 days |
| **Uber API** | Rides | Medium | 3 days |
| **Health Connect** | Wearables | Medium | 3 days |
| **FCM** | Push notifications | Medium | 2 days |
| **WhatsApp Business** | Messaging | Low | 3 days |
| **ROS 2** | Robotics | Low | 10 days |

---

## Part 6: Decision Log

| Decision | Alternatives | Why This |
|----------|--------------|---------|
| Use existing orchestrator instead of new agent framework | Buy OpenAI Agents, Build from scratch | 17KB working code already handles subagents, planning, tool use |
| Use faster-whisper over cloud STT | Cloud APIs, Whisper API | Local + private + fast as designed |
| Use Coqui TTS over cloud TTS | Cloud APIs, ElevenLabs | Local voice cloning with consent |
| Reuse communication service for commerce | New commerce service | Channel registry pattern already supports multi-provider |
| Add robotics last | Build now, buy robot | Phase 6 - requires hardware investment |

---

## Part 7: Success Criteria

### MVP (Month 1)

- [ ] All Phase 1 tasks complete
- [ ] Core chat working with all tool lanes
- [ ] Computer-use browser automation
- [ ] Local STT + TTS working
- [ ] Alpha Vantage finance data

### Phase 2 (Month 2)

- [ ] Voice calling via Twilio
- [ ] Food/ride ordering working
- [ ] Smart-home control enhanced
- [ ] Push notifications

### Phase 3 (Month 3)

- [ ] Vision (object detection + OCR)
- [ ] Health/wearables integration
- [ ] Mobile companion functional

### Full (Month 4+)

- [ ] All 18 capabilities operational
- [ ] Robotics integration ready

---

## Appendix: Key Files Reference

| What | File |
|------|------|
| Main app | `backend/main.py` |
| Orchestrator service | `services/orchestrator/service.py` |
| Memory service | `services/memory/service.py` |
| Tools executor | `services/tools/executor.py` |
| MCP bridge | `services/tools/mcp_bridge.py` |
| Audio service | `services/audio/service.py` |
| Vision service | `services/vision/service.py` |
| Config | `infrastructure/config.py` |
| Domain contracts | `domain/*/contracts.py` |

---

*Generated: 2026-04-20*