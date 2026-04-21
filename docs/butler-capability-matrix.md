# Butler Capability Matrix - Full Product Specification

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## Executive Summary

This document presents the complete Butler capability matrix consolidating all features into a single coherent ambient AI OS. No MVP - full product rollout only.

### Product Vision

> Butler is an open ambient AI OS that understands people, devices, places, and workflows in real time, then acts safely across voice, screen, web, home, health, enterprise, and robots.

---

## Capability Matrix

### Category 1: Ambient Personal AI

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 1.1 | Full-duplex voice assistant | openWakeWord + Silero VAD + WhisperX + TTS | Audio Pipeline | Medium | Premium |
| 1.2 | Wake word detection | openWakeWord | Wake Service | Low | Premium |
| 1.3 | Verified direct commands | ECAPA-TDNN + custom classifier | Speaker ID + Command Classifier | Medium | Premium |
| 1.4 | Multimodal input | Vision + Audio + Text MCPs | Vision Service, Audio Service | Medium | Premium |
| 1.5 | Context carryover | Dialogue state tracker | Memory Service | Low | Premium |
| 1.6 | Follow mode (30-60s active) | Turn state machine | Conversation Manager | Low | Premium |
| 1.7 | Natural interruption handling | Barge-in classifier | Audio Pipeline | Medium | Premium |
| 1.8 | Conversational memory | PostgreSQL + vector | Memory Service | Low | Premium |

---

### Category 2: Cross-Device Presence & Proximity

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 2.1 | Nearest device selection | Ranging + context | Device Manager | Medium | Premium |
| 2.2 | Indoor proximity behaviors | UWB + BLE + Wi-Fi RTT | Ranging Service | Medium | Premium |
| 2.3 | Precise ranging (10cm) | Android Ranging API | Ranging Service | Medium | Premium |
| 2.4 | Device-aware output | Context + device graph | Device Manager | Low | Premium |
| 2.5 | Handoff when close | Ranging trigger | Automation Engine | Medium | Premium |
| 2.6 | Find my stuff | UWB + BLE | Ranging Service | Low | Premium |
| 2.7 | Unlock when near | UWB + trust policy | Security Service | High | Premium |
| 2.8 | Multi-device session continuity | Session sync | Sync Service | Low | Premium |

---

### Category 3: Smart-Home & Environment Control

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 3.1 | Light control | Matter + Home Assistant | Home Service | Low | Premium |
| 3.2 | Lock control | Matter + integration | Security Service | High | Premium |
| 3.3 | Climate control | Matter + HVAC | Home Service | Low | Premium |
| 3.4 | Plug/switch control | Matter | Home Service | Low | Premium |
| 3.5 | Blind/shade control | Matter | Home Service | Low | Premium |
| 3.6 | Vacuum/robot control | Manufacturer APIs | Home Service | Low | Premium |
| 3.7 | Camera streaming | WebRTC + Home Assistant | Media Service | High | Premium |
| 3.8 | Speaker multi-room audio | Cast + AirPlay + Snapcast | Media Service | Low | Premium |
| 3.9 | TV control | CEC + IR + Matter | Media Service | Low | Premium |
| 3.10 | Multi-admin coexistence | Matter multi-admin | Home Service | Medium | Premium |
| 3.11 | Local automations | Home Assistant | Automation Engine | Medium | Premium |
| 3.12 | Scenes and routines | Home graph | Automation Engine | Low | Premium |
| 3.13 | Offline fallbacks | Local-first design | Resilience Service | Medium | Premium |
| 3.14 | Home graph mapping | Entity mapping | Home Service | Low | Premium |
| 3.15 | Device trust states | Trust policy engine | Security Service | Medium | Premium |

---

### Category 4: Computer Control & Digital Operator

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 4.1 | Browser automation | Playwright MCP | Computer Service | High | Premium |
| 4.2 | Shell/terminal commands | SSH + shell MCP | Computer Service | High | Premium |
| 4.3 | Application control | macOS/Windows APIs | Computer Service | High | Premium |
| 4.4 | File management | Filesystem MCP | Computer Service | Medium | Premium |
| 4.5 | Form filling | Browser + vision | Computer Service | Medium | Premium |
| 4.6 | Document drafting | Text generation | Computer Service | Low | Premium |
| 4.7 | Calendar management | CalDAV + Graph API | Computer Service | Medium | Premium |
| 4.8 | Email automation | SMTP + IMAP | Computer Service | High | Premium |
| 4.9 | Multi-step workflows | Workflow engine | Orchestrator | High | Premium |
| 4.10 | MCP tool interoperability | MCP Registry + custom servers | Tool Bridge | Medium | Premium |
| 4.11 | Approval-gated execution | Policy engine | Orchestrator | High | Premium |
| 4.12 | Workflow persistence | PostgreSQL | Orchestrator | Low | Premium |

---

### Category 5: Deep Research & Knowledge

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 5.1 | Web research | Exa + web search | Research Service | Low | Premium |
| 5.2 | File research | Agent Brain | Research Service | Low | Premium |
| 5.3 | Citation-backed answers | RAG + citation tracking | Knowledge Service | Medium | Premium |
| 5.4 | Multi-source synthesis | Multi-agent retrieval | Research Service | Medium | Premium |
| 5.5 | Notebook research memory | PostgreSQL + vector | Knowledge Service | Low | Premium |
| 5.6 | Source graphing | Knowledge graph | Knowledge Service | Low | Premium |
| 5.7 | Quote extraction | Agent Brain | Knowledge Service | Low | Premium |
| 5.8 | Contradiction tracking | Multi-source comparison | Knowledge Service | Medium | Premium |
| 5.9 | Persistent entity graph | Knowledge graph | Knowledge Service | Low | Premium |
| 5.10 | Automatic briefings | Summary generation | Knowledge Service | Low | Premium |
| 5.11 | "What changed" tracking | Diff tracking | Knowledge Service | Low | Premium |
| 5.12 | Fact verification | Multi-source retrieval | Knowledge Service | Medium | Premium |
| 5.13 | Executive summaries | LLM summarization | Knowledge Service | Low | Premium |

---

### Category 6: Realtime Meeting & Call Copilot

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 6.1 | Live transcription | WhisperX + pyannote | Meeting Service | Medium | Premium |
| 6.2 | Realtime speaker diarization | pyannote | Meeting Service | Medium | Premium |
| 6.3 | Multilingual STT | Azure Speech | Translation Service | Medium | Premium |
| 6.4 | Multilingual TTS | Azure Speech | Translation Service | Low | Premium |
| 6.5 | Live speech-to-speech translation | Azure Speech realtime | Translation Service | High | Premium |
| 6.6 | Meeting summaries | LLM summarization | Meeting Service | Low | Premium |
| 6.7 | Action item extraction | NER + classification | Meeting Service | Medium | Premium |
| 6.8 | Risk flag detection | Intent classification | Meeting Service | Medium | Premium |
| 6.9 | Follow-up drafting | Text generation | Meeting Service | Low | Premium |
| 6.10 | Interpreter mode | Azure Speech realtime | Translation Service | High | Premium |
| 6.11 | Coaching overlay | Realtime TTS | Coaching Service | Medium | Premium |
| 6.12 | Post-meeting documentation | Doc generation | Meeting Service | Low | Premium |

---

### Category 7: Health, Fitness & Wellbeing

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 7.1 | Sleep-aware assistant | HealthKit + Health Connect | Health Service | Medium | Premium |
| 7.2 | Workout-aware assistant | HealthKit + Health Connect | Health Service | Medium | Premium |
| 7.3 | Recovery-aware planning | HealthKit + Health Connect | Health Service | Medium | Premium |
| 7.4 | Health summaries | HealthKit + Health Connect | Health Service | Low | Premium |
| 7.5 | Habit coaching | Habit tracking | Health Service | Low | Premium |
| 7.6 | Medication reminders | Scheduling | Health Service | Medium | Premium |
| 7.7 | Hydration nudges | Scheduling | Health Service | Low | Premium |
| 7.8 | Posture/activity prompts | HealthKit motion | Health Service | Low | Premium |
| 7.9 | Safety escalation rules | Policy engine | Health Service | High | Premium |
| 7.10 | Privacy-preserving automations | Consent engine | Health Service | High | Premium |
| 7.11 | User-controlled permissions | Health Connect | Health Service | Medium | Premium |
| 7.12 | Emergency detection | Health data + policy | Health Service | High | Premium |

---

### Category 8: Mobility, Travel & In-World Assistance

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 8.1 | Trip planning | Travel APIs + search | Mobility Service | Medium | Premium |
| 8.2 | Navigation-aware reminders | Maps + location | Mobility Service | Low | Premium |
| 8.3 | Airport/rail coordination | Transit APIs | Mobility Service | Low | Premium |
| 8.4 | Car mode (voice-first) | Android Auto / CarPlay | Mobility Service | Medium | Premium |
| 8.5 | Geo-aware routines | Location triggers | Automation Engine | Medium | Premium |
| 8.6 | "When I arrive" triggers | Geofencing | Mobility Service | Medium | Premium |
| 8.7 | "When I leave" triggers | Geofencing | Mobility Service | Medium | Premium |
| 8.8 | Nearby intelligence | Ranging + maps | Mobility Service | Low | Premium |
| 8.9 | Lost item/location assistance | Ranging + BLE | Mobility Service | Medium | Premium |
| 8.10 | Charging station navigation | EV APIs | Mobility Service | Low | Premium |

---

### Category 9: Commerce & Life Admin

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 9.1 | Grocery ordering | Retail APIs | Commerce Service | High | Premium |
| 9.2 | Food ordering | Delivery APIs | Commerce Service | High | Premium |
| 9.3 | Cab/ticket booking | Transport + ticketing | Commerce Service | High | Premium |
| 9.4 | Subscription management | Tracking + renewal | Commerce Service | Medium | Premium |
| 9.5 | Refund processing | Retail APIs | Commerce Service | High | Premium |
| 9.6 | Bill reminders | Scheduling | Commerce Service | Low | Premium |
| 9.7 | Email triage | Email MCP + classification | Computer Service | High | Premium |
| 9.8 | Calendar negotiation | CalDAV + ML | Computer Service | Medium | Premium |
| 9.9 | Approval flows | Workflow engine | Orchestrator | High | Premium |
| 9.10 | Document extraction | Vision + OCR | Computer Service | Medium | Premium |
| 9.11 | Form filling automation | Browser + vision | Computer Service | High | Premium |
| 9.12 | "Answer for me" mode | LLM + search | Commerce Service | Medium | Premium |
| 9.13 | Price watching + alerts | Monitoring | Commerce Service | Low | Premium |
| 9.14 | Autonomous policy gates | Policy engine | Orchestrator | High | Premium |

---

### Category 10: Enterprise & Team OS

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 10.1 | Team meeting copilot | Meeting Service | Team Service | Medium | Premium |
| 10.2 | CRM integration | Salesforce/HubSpot MCP | Team Service | Medium | Premium |
| 10.3 | Ticket management | Jira/Linear MCP | Team Service | Medium | Premium |
| 10.4 | Document collaboration | Google/Notion MCP | Team Service | Low | Premium |
| 10.5 | Analytics access | Database MCPs | Team Service | Medium | Premium |
| 10.6 | Incident response | Automation + paging | Team Service | High | Premium |
| 10.7 | Onboarding workflows | Workflow engine | Team Service | Medium | Premium |
| 10.8 | Shared memory | PostgreSQL + ACLs | Team Service | Medium | Premium |
| 10.9 | Multi-tenant permissions | ACL + namespaces | Team Service | High | Premium |
| 10.10 | Audit trails | Logging + export | Observability | High | Premium |
| 10.11 | Internal knowledge access | MCP connectors | Knowledge Service | Medium | Premium |

---

### Category 11: Robotics & Embodied Agents

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 11.1 | Robot integration | ROS 2 bridge | Robotics Service | High | Premium |
| 11.2 | Camera perception | Vision Service | Robotics Service | Medium | Premium |
| 11.3 | Audio perception | Audio Service | Robotics Service | Medium | Premium |
| 11.4 | Ranging integration | UWB + ROS | Robotics Service | Medium | Premium |
| 11.5 | Mobile node deployment | ROS + Tailscale | Robotics Service | High | Premium |
| 11.6 | Manipulation planning | Motion planning | Robotics Service | High | Premium |
| 11.7 | Navigation | ROS navigation | Robotics Service | High | Premium |
| 11.8 | Telepresence | WebRTC + ROS | Robotics Service | High | Premium |
| 11.9 | Local autonomy | Edge AI | Robotics Service | High | Premium |
| 11.10 | Simulation testing | Gazebo | Robotics Service | Medium | Premium |
| 11.11 | Physical/sim pipelines | Mixed pipeline | Robotics Service | High | Premium |
| 11.12 | Human-robot task planning | Task planning | Robotics Service | High | Premium |
| 11.13 | Approval-aware execution | Policy engine | Robotics Service | High | Premium |

---

### Category 12: Cameras, Media & Live Visual Intelligence

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 12.1 | Low-latency camera streams | WebRTC | Media Service | High | Premium |
| 12.2 | Remote inspection | WebRTC + vision | Media Service | Medium | Premium |
| 12.3 | Security monitoring | Vision + alerts | Media Service | High | Premium |
| 12.4 | Smart notifications | Vision + routing | Media Service | Medium | Premium |
| 12.5 | Cross-device streaming | WebRTC + Tailscale | Media Service | Medium | Premium |
| 12.6 | Remote assistance | WebRTC + vision | Media Service | High | Premium |
| 12.7 | Shared viewing | WebRTC + sync | Media Service | Low | Premium |
| 12.8 | Teleoperation | WebRTC + control | Media Service | High | Premium |
| 12.9 | Visual QA | Vision model | Vision Service | Medium | Premium |
| 12.10 | Object recognition | GroundingDINO + SAM 2 | Vision Service | Medium | Premium |
| 12.11 | Person/face recognition | InsightFace | Vision Service | High | Premium |
| 12.12 | Screen understanding | Vision + OCR | Vision Service | Medium | Premium |
| 12.13 | Document reading | OCR + vision | Vision Service | Low | Premium |
| 12.14 | Camera handoff | Device graph | Media Service | Medium | Premium |

---

### Category 13: Open Ecosystem & Community

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 13.1 | Skill marketplace | Registry service | Ecosystem | Medium | Premium |
| 13.2 | Plugin registry | MCP Registry | Ecosystem | Low | Premium |
| 13.3 | External tool servers | MCP Bridge | Tool Bridge | Medium | Premium |
| 13.4 | Community nodes | Open contribution | Ecosystem | Medium | Premium |
| 13.5 | Device packs | Prebuilt configs | Ecosystem | Low | Premium |
| 13.6 | Workflow templates | Community share | Ecosystem | Low | Premium |
| 13.7 | Dashboards | Visualization | Ecosystem | Low | Premium |
| 13.8 | Signed packages | Security signing | Security Service | High | Premium |
| 13.9 | Trust pipelines | Supply chain verification | Security Service | High | Premium |
| 13.10 | Rollback lifecycle | Version management | Deployment | Medium | Premium |

---

### Category 14: Reliability, Cyber & Operator Plane

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 14.1 | Full traces | OpenTelemetry | Observability | Medium | Premium |
| 14.2 | Metrics collection | OpenTelemetry | Observability | Low | Premium |
| 14.3 | Structured logs | OpenTelemetry | Observability | Low | Premium |
| 14.4 | Model call tracking | Span tracking | Observability | Medium | Premium |
| 14.5 | Workflow step tracking | Span tracking | Observability | Medium | Premium |
| 14.6 | Device action audit | Event logging | Observability | High | Premium |
| 14.7 | Plugin event tracking | Event logging | Observability | Medium | Premium |
| 14.8 | Zero Trust mesh | Tailscale | Security Service | High | Premium |
| 14.9 | End-to-end encryption | Tailscale | Security Service | High | Premium |
| 14.10 | Admin surfaces | Dashboard + API | Operator | High | Premium |
| 14.11 | Health state monitoring | Health checks | Operator | Low | Premium |
| 14.12 | Rollout controls | Deployment | Operator | High | Premium |
| 14.13 | Canary releases | Deployment | Operator | Medium | Premium |
| 14.14 | Incident tooling | Paging + runbooks | Operator | High | Premium |
| 14.15 | Audit for sensitive actions | Logging + export | Security | High | Premium |

---

### Category 15: Vision Intelligence

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 15.1 | Open-world detection | GroundingDINO 1.6 | Vision Service | Medium | Premium |
| 15.2 | Segmentation | SAM 2 / Grounded SAM 2 | Vision Service | Medium | Premium |
| 15.3 | Face recognition | InsightFace / ArcFace | Vision Service | High | Premium |
| 15.4 | Face verification | ECAPA-TDNN | Vision Service | High | Premium |
| 15.5 | Person ReID | OSNet / FastReID | Vision Service | Medium | Premium |
| 15.6 | Vehicle ReID | FastReID vehicle | Vision Service | Medium | Premium |
| 15.7 | License plate OCR | CRNN | Vision Service | Medium | Premium |
| 15.8 | Multi-object tracking | ByteTrack | Vision Service | Medium | Premium |
| 15.9 | Multi-camera fusion | DeepStream MV3DT | Vision Service | High | Premium |
| 15.10 | Human-vehicle relations | Graph reasoning | Vision Service | Medium | Premium |
| 15.11 | Ownership inference | Temporal graph | Vision Service | Medium | Premium |
| 15.12 | Confidence-aware output | Soft claims | Vision Service | Low | Premium |
| 15.13 | Consent management | Consent engine | Security | High | Premium |

---

### Category 16: Audio Intelligence

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 16.1 | Wake word detection | openWakeWord | Audio Service | Low | Premium |
| 16.2 | Voice activity detection | Silero VAD | Audio Service | Low | Premium |
| 16.3 | Speaker diarization | pyannote | Audio Service | Medium | Premium |
| 16.4 | Speaker verification | ECAPA-TDNN | Audio Service | High | Premium |
| 16.5 | ASR with timestamps | WhisperX | Audio Service | Medium | Premium |
| 16.6 | Source separation | Asteroid | Audio Service | Medium | Premium |
| 16.7 | Acoustic event detection | Custom classifier | Audio Service | Medium | Premium |
| 16.8 | Enrollment management | Voice enrollment | Audio Service | High | Premium |
| 16.9 | Multi-language support | Azure Speech | Translation Service | Medium | Premium |

---

### Category 17: Realtime Listening & Conversation

| # | Feature | SOTA Stack | Required Services | Risk Level | Implementation |
|---|---------|-----------|-----------------|-----------|----------------|
| 17.1 | Turn-taking prediction | Custom acoustic-linguistic | Audio Service | Medium | Premium |
| 17.2 | Importance scoring | Custom classifier | Audio Service | Medium | Premium |
| 17.3 | Barge-in handling | VAD + classifier | Audio Service | Medium | Premium |
| 17.4 | Backchannel detection | Pattern matching | Audio Service | Low | Premium |
| 17.5 | Pre-wakeup commands | Directed classifier | Audio Service | Medium | Premium |
| 17.6 | Activation policies | Policy engine | Security | Medium | Premium |
| 17.7 | Reference resolution | Dialogue state | Memory | Medium | Premium |
| 17.8 | Entity tracking | Active entity stack | Memory | Low | Premium |
| 17.9 | Claim tracking | Claim stack | Memory | Medium | Premium |
| 17.10 | Contextual clarification | Resolution API | Memory | Medium | Premium |

---

## Service Dependency Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUTLER SERVICES                          │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │                  CORE SERVICES                      │ │
│  ├─────────────────────────────────────────────────────┤ │
│  │  Gateway          - API entry, auth, rate limit   │ │
│  │  Orchestrator      - Workflow, task execution       │ │
│  │  Memory            - Dialogue, entity, claim store  │ │
│  │  Security          - Authz, audit, consent         │ │
│  │  Observability     - Traces, metrics, logs         │ │
│  └─────────────────────────────────────────────────────┘ │
│                         │                                 │
│  ┌─────────────────────────────────────────────────────┐ │
│  │               PERCEPTION SERVICES                   │ │
│  ├─────────────────────────────────────────────────────┤ │
│  │  Audio Service    - Wake, VAD, ASR, TTS            │ │
│  │  Vision Service   - Detection, recognition, ReID  │ │
│  │  Meeting Service - Transcription, translation      │ │
│  │  Translation     - Multilingual speech           │ │
│  └─────────────────────────────────────────────────────┘ │
│                         │                                 │
│  ┌─────────────────────────────────────────────────────┐ │
│  │               DOMAIN SERVICES                       │ │
│  ├───────────────��─��───────────────────────────────────┤ │
│  │  Home Service    - Matter, HA, smart devices      │ │
│  │  Device Manager  - Ranging, proximity, handoff     │ │
│  │  Mobility Service - GPS, trips, transport        │ │
│  │  Health Service   - HealthKit, Health Connect   │ │
│  │  Commerce Service - Orders, payments, subscriptions│ │
│  │  Team Service     - Collaboration, permissions     │ │
│  │  Robotics Service- ROS, navigation, manipulation │ │
│  │  Media Service   - Streaming, WebRTC              │ │
│  │  Research Service- Web, file, knowledge work      │ │
│  │  Computer Service- Browser, shell, automation   │ │
│  │  Knowledge Service - Graph, RAG, citations       │ │
│  └─────────────────────────────────────────────────────┘ │
│                         │                                 │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              INFRASTRUCTURE SERVICES                 │ │
│  ├─────────────────────────────────────────────────────┤ │
│  │  Database        - PostgreSQL + pgvector           │ │
│  │  Cache           - Redis                            │ │
│  │  Queue           - Redis Streams                    │ │
│  │  Search         - Agent Brain + Exa                │ │
│  │  Mesh Network   - Tailscale                       │ │
│  │  MCP Registry   - Tool discovery                  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Risk Matrix

| Risk Level | Categories | Approval Required |
|------------|-------------|-------------------|
| **Low** | Core features, memory, observation | Auto-deploy |
| **Medium** | Home control, computer automation, meeting | Review + sign-off |
| **High** | Security, health, commerce, robotics, finance | Manual approval + audit |

---

## Implementation Priority (Phase Order)

### Phase 1: Foundation (Weeks 1-4)
- Core services (Gateway, Orchestrator, Memory, Security)
- Database + Cache + Mesh
- OpenTelemetry integration
- Basic voice pipeline

### Phase 2: Perception (Weeks 5-8)
- Wake word + VAD + ASR
- Turn-taking + barge-in
- Vision detection basics
- Meeting transcription

### Phase 3: Home & Device (Weeks 9-12)
- Matter + Home Assistant
- Ranging + proximity
- Multi-device handoff
- Smart notifications

### Phase 4: Productivity (Weeks 13-16)
- Computer automation
- Research + knowledge
- Meeting copilot
- Commerce basics

### Phase 5: Advanced (Weeks 17-20)
- Robotics integration
- Health + wellbeing
- Enterprise features
- Community platform

### Phase 6: Polish (Weeks 21-24)
- Performance tuning
- Security audit
- Documentation
- Release

---

## Feature Count Summary

| Category | Features | Risk Distribution |
|----------|----------|--------------------|
| Ambient Personal AI | 8 | 1L, 6M, 1H |
| Cross-Device | 8 | 2L, 5M, 1H |
| Smart-Home | 15 | 10L, 4M, 1H |
| Computer Control | 12 | 1L, 3M, 8H |
| Research | 13 | 9L, 4M |
| Meeting | 12 | 3L, 6M, 3H |
| Health | 12 | 4L, 3M, 5H |
| Mobility | 10 | 7L, 3M |
| Commerce | 14 | 2L, 4M, 8H |
| Enterprise | 11 | 2L, 4M, 5H |
| Robotics | 13 | 1L, 2M, 10H |
| Media | 14 | 5L, 4M, 5H |
| Ecosystem | 10 | 5L, 3M, 2H |
| Reliability | 15 | 4L, 3M, 8H |
| Vision | 13 | 4L, 6M, 3H |
| Audio | 9 | 3L, 5M, 1H |
| Realtime | 10 | 5L, 4M, 1H |
| **TOTAL** | **177** | **58L, 63M, 56H** |

---

## Build Commitment

This is the 100% pure product specification. No MVP. No staged rollouts. Full production capability from day one.

| Phase | Duration | Deliverables |
|-------|----------|------------|
| Foundation | 4 weeks | Core infrastructure, voice pipeline |
| Perception | 4 weeks | Audio + Vision intelligence |
| Home | 4 weeks | Smart environment control |
| Productivity | 4 weeks | Work tools + research |
| Advanced | 4 weeks | Robotics + health + enterprise |
| Polish | 4 weeks | Ship-ready product |

**Total Features: 177**  
**Low Risk: 58 (33%)**  
**Medium Risk: 63 (36%)**  
**High Risk: 56 (31%)**  

---

**End of Specification**