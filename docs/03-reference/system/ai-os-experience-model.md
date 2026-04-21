# Butler AI OS Experience Model

> **Version:** 1.0  
> **Updated:** 2026-04-19  
> **Owner:** Butler Product + Architecture Team

---

## What Butler Is

**Butler is a personal AI operating system.**

It is not a chatbot wrapper, not a feature add-on, and not a hosted AI service that the user visits. Butler is sovereign software — a cloud-and-device runtime that the user owns, that remembers everything they permit, that acts autonomously within their policy, and that improves with them over time.

Butler operates across two simultaneous tracks:

- **Personal assistant track** — a deeply personalized, memory-driven AI companion
- **Multi-tenant AI platform track** — a governed, scalable AI OS for teams, enterprises, and developers

---

## The Five Modes

### 1. Personal Assistant Mode

**What it does:**
- Conversational AI interaction through any channel (web, mobile, voice, message apps)
- Memory-backed responses using the user's digital twin (episodic, facts, preferences, graph)
- Proactive suggestions based on calendar, habits, and context
- Tool execution within user-approved boundaries

**Experience feel:**
- Feels like talking to someone who genuinely knows you
- Remembers context from months ago without being reminded
- Anticipates needs before they're stated
- Operates as a background presence, not just a chat window

### 2. Platform Mode

**What it does:**
- Multi-user, multi-tenant deployment
- Team-shared agents and capability libraries
- Operator dashboards, audit trails, compliance controls
- API-first: developers build on Butler via REST and MCP

**Experience feel:**
- Enterprise-grade reliability with personal-AI quality
- Each user gets a fully personalized experience within their tenant's policy
- Operators have full visibility and control without compromising user privacy

### 3. Device Mode

**What it does:**
- Butler runs on or alongside the user's devices (iOS, Android, macOS, desktop)
- Ambient capture: microphone, camera, screen — with explicit consent
- Local RAG memory for offline recall
- Companion surfaces: menu-bar app, overlay, notification integration
- Device control: triggers actions on the device (calendar, files, apps)

**Experience feel:**
- Butler is always there, invisibly, until needed
- Voice activation without opening an app
- Screen-aware: can see what the user is looking at and respond contextually
- Works offline for common recall operations

### 4. Memory Mode

**What it does:**
- Butler's memory graph browser — explore, edit, manage the digital twin
- Review what Butler knows, correct errors, delete sensitive facts
- Upload documents and have them indexed for future recall
- Manage notebooks: curated knowledge workspaces
- Consent management: see exactly what data is stored and in which tier

**Experience feel:**
- Total transparency and control over Butler's knowledge of you
- Like a personal knowledge base that grows intelligently with every interaction
- User is always in control: delete anything, any time, with immediate effect

### 5. Operator Mode

**What it does:**
- Butler's control plane for administrators and platform engineers
- Cluster health and circuit breaker dashboard
- Tool approval queue (ACP)
- Emergency controls (drain, kill switches, break-glass)
- Audit log access and compliance reporting
- Doctor diagnostic runs and self-healing

**Experience feel:**
- Production operations feel, not a toy admin panel
- Full observability: every metric, every circuit breaker, every audit event
- Emergency controls are one click away, always audited

---

## Cloud + Device Runtime

Butler is a **dual-runtime system**:

| Runtime | Where it runs | Role |
|---|---|---|
| **Cloud runtime** | Butler backend (FastAPI + PostgreSQL + Redis + Neo4j + Qdrant) | Persistent memory, orchestration, ML, tool execution, policy |
| **Device runtime** | User's phone, computer, or companion device | Ambient capture, local RAG, UI, offline recall |

The two runtimes are synchronized via Hermes (session transport) and Butler's node registry (Redis-based). Device nodes register themselves with the cluster, send heartbeats, and receive capability updates.

**Device-cloud boundary rules:**
- Identity and auth: always cloud-authoritative
- Memory: cloud-primary with device cache
- Tool execution: L0/L1 tools may run device-local; L2/L3 always cloud-side
- Ambient capture: device-local until session opened, then streamed to cloud (with consent)

---

## Memory-Driven Personal Digital Twin

Every response Butler gives is shaped by the user's digital twin:

```
User message
    │
    ▼
[Recall] → search episodic memory, knowledge graph, preferences, uploaded files
    │
    ▼
[Contextualize] → inject relevant memories into agent context (personalization engine)
    │
    ▼
[Respond] → LLM response informed by memory, not just the current message
    │
    ▼
[Update] → extract new facts/entities from conversation → update memory graph
```

The digital twin is not just a conversation log. It is:
- A knowledge graph of entities and relationships
- A timeline of episodic events
- A profile of preferences and behavioral patterns
- A notebook of user-curated knowledge
- A consented, opt-in candidate for model improvement

---

## Policy-Governed Action Engine

Butler acts — it doesn't just chat. Every action is governed:

```
Agent decides to take action
    │
    ▼
[Risk classification] → L0 (safe) → L3 (high-risk)
    │
    ├── L0/L1 → execute immediately (within quota)
    ├── L2 → execute with audit log + post-hoc user notification
    └── L3 → ACP: request human approval before execution
```

No action is irreversible without explicit human approval. No tool escalates beyond the policy of its risk tier without breaking glass.

---

## Sub-Agent Deployment Platform

Butler is also a **platform for deploying specialized AI agents**:

- Parent agent spawns sub-agents for parallel or specialized tasks
- Sub-agents are first-class: identity, budget, sandbox, audit trail
- Sub-agents can run in-process (fast) or in isolated containers (safe) or on device (ambient)
- Developer APIs for custom sub-agent deployment
- Marketplace for community and enterprise sub-agent capabilities

---

## Product Identity

**Butler is the AI OS for people who take their data seriously and want AI that actually knows them.**

Five sentences that define Butler:

1. Butler is **cloud and device** — it runs everywhere you are.
2. Butler **remembers** — not just conversations, but a living knowledge graph of your world.
3. Butler **acts** — safely, auditably, within the policy you set.
4. Butler **improves** — it learns from you over time, with your explicit consent.
5. Butler is **yours** — you own your data, your memory, your agent, and your controls.

---

## Reference

- `docs/README.md` — System overview
- `docs/01-core/PRD.md` — Product requirements
- `docs/00-governance/platform-constitution.md` — System governance rules
- `docs/03-reference/system/digital-twin-memory.md` — Memory architecture
- `docs/03-reference/agent/subagent-runtime.md` — Sub-agent deployment
- `docs/03-reference/system/operator-plane.md` — Operator control plane


## Harvested Capabilities: AI OS Experience
**Source: natively-cluely-ai-assistant**
- **Stealth & Intracompany Context Integration:** Blurring the line between application boundaries. The OS operates globally (screen overlay, system audio) rather than being trapped in a browser window.
- **Persona Context Switching:** Instant transition of agent behaviors and memory pools based on visual cues or active window heuristics.

**Source: Vane & OpenClaw**
- **Parallel Action Feedback:** Non-blocking UX showing the operator progress as background routines (web search, vector ingestion, coding analysis) execute asynchronously.
- **Visual Canvas Sandbox:** A collaborative agent-to-human whiteboard (A2UI) that provides an infinite spatial workspace for arranging outputs iteratively.

