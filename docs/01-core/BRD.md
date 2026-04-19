# BRD - Business Requirements Document

> **For:** Product, Leadership, Engineering
> **Status:** v0.3 (Production-Ready)
> **Version:** 3.0
> **Reference:** Corrected specification with boundary fixes, production targets

---

## 1. Executive Summary

**Butler** is an AI-powered personal assistant that executes tasks on behalf of users across multiple platforms (messaging, email, calendar, automation).

**Vision:** Replace app-switching with a single conversational interface that handles complex multi-step tasks autonomously.

**Target:** 1M users within 24 months.

---

## 2. Problem Statement

### 2.1 Current Pain Points

| Pain | Impact |
|------|--------|
| App fragmentation | Users manage 20+ apps daily |
| Repetitive tasks | Same actions repeated (ordering food, sending messages) |
| Context switching | High cognitive load switching between apps |
| Missing automation | No unified way to automate cross-app workflows |
| Passive assistants | Current assistants only respond, don't act |

### 2.2 Market Gap

- **Siri/Alexa**: Voice-only, limited actions, no learning
- **ChatGPT**: Conversational but no execution capability
- **TaskRabbit**: Human-based, not AI-driven
- **Zapier**: Technical setup required, no natural language

**Gap:** No AI assistant that understands intent AND executes actions autonomously.

---

## 3. Target Users

### 3.1 Primary Persona

| Attribute | Value |
|-----------|-------|
| Age | 25-45 |
| Tech proficiency | Medium to High |
| Pain | Time poverty, app fatigue |
| Willingness | Pay for time savings |
| Use case | Task execution, automation |

### 3.2 Secondary Persona

- Power users wanting workflow automation
- Enterprise users needing team coordination
- Accessibility users wanting voice-first interface

---

## 4. Value Proposition

### 4.1 Core Value

> **"Tell Butler what to do, and it gets done."**

### 4.2 Differentiation

| Competitor | Butler's Advantage |
|------------|--------------------|
| Siri | Learns habits, executes complex workflows |
| ChatGPT | Real action execution, memory |
| Zapier | Natural language setup |
| TaskRabbit | AI-driven, instant, cheaper |

### 4.3 Key Benefits

1. **Time savings** - Reduce task time by 80%
2. **Cognitive relief** - Single interface for all tasks
3. **Personalization** - Learns your preferences
4. **Proactive** - Suggests actions before asked
5. **Cross-platform** - Unified control of apps

---

## 5. Success Metrics (KPIs)

### 5.1 User Metrics

| Metric | Target (12 months) |
|--------|---------------------|
| MAU | 100K |
| DAU | 30K |
| DAU/MAU | 30% |
| Task completion rate | >85% |

### 5.2 Engagement Metrics

| Metric | Target |
|--------|--------|
| Avg tasks/day/user | 5 |
| Session length | <2 min (efficient) |
| Retention D30 | >40% |
| Retention D90 | >20% |

### 5.3 Business Metrics

| Metric | Target |
|--------|--------|
| CAC | <$15 |
| LTV | >$120 |
| LTV/CAC | >8x |
| Premium conversion | >10% |

---

## 6. Core Features

### 6.1 Phase 1 Features (Launch)

| Feature | Description |
|---------|-------------|
| Messaging | Send SMS, WhatsApp, iMessage |
| Search | Web search with RAG |
| Reminders | Set reminders, alarms |
| Q&A | Answer questions with context |
| Memory | Remember user preferences |

### 6.2 Phase 2 Features

| Feature | Description |
|---------|-------------|
| Automation | Cross-app workflows |
| Voice | Full voice interface |
| Vision | Screen understanding |
| Recommendations | Proactive suggestions |

### 6.3 Phase 3 Features

| Feature | Description |
|---------|-------------|
| Prediction | Next action prediction |
| Learning | Pattern detection |
| Calling | Phone calls |
| Email | Send/read emails |

---

## 7. User Flows

### 7.1 Primary Flow: Task Execution

```text
User Input → Intent Detection → Context Retrieval →
Action Planning → Tool Execution → Verification → Response
```

### 7.2 Example Flows

**Flow 1: Send Message**
```
User: "Text mom I'll be home at 7"
→ Intent: send_message
→ Entity: mom, "I'll be home at 7"
→ Memory: mom's number
→ Execute: Send SMS
→ Verify: Confirm sent
→ Response: "Sent to mom ✓"
```

**Flow 2: Order Food**
```
User: "Order pizza from Italian Place"
→ Intent: order_food
→ Entity: pizza, Italian Place
→ Memory: user's address, payment
→ Execute: Open app → order → pay
→ Verify: Order confirmation
→ Response: "Ordered. Arriving 30 mins ✓"
```

---

## 8. Non-Goals (Out of Scope)

| Out of Scope | Reason |
|--------------|--------|
| Physical tasks | Robots/delivery not supported |
| Financial transactions | High risk, regulatory complexity |
| Medical advice | Liability concerns |
| Legal advice | Liability concerns |
| Hardware control | Beyond mobile scope |

---

## 9. Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Privacy concerns | High | High | Clear opt-in, local-first, minimal data |
| Tool integration failures | Medium | High | Graceful degradation, fallback to manual |
| AI hallucination | Medium | High | Verification layer, human-in-loop option |
| Platform lock-in | Low | Medium | Modular tool system, standard APIs |

---

## 10. Roadmap

| Phase | Timeline | Focus |
|-------|----------|-------|
| Phase 1 | Months 1-3 | Core chat + memory + basic tools |
| V1 | Months 4-6 | Voice + automation + recommendations |
| V2 | Months 7-12 | Prediction + learning + enterprise |

---

## 11. Performance Targets

| Metric | Target | P50 | P95 | P99 |
|--------|--------|-----|-----|-----|
| Response time (simple) | <500ms | 100ms | 300ms | 500ms |
| Response time (complex) | <3s | 1s | 2s | 3s |
| Task completion rate | >85% | 90% | 85% | 80% |
| Concurrent users | 50K | - | - | - |
| Peak RPS | 10K | 5K | 8K | 10K |

---

## 12. Protocol Standards

| Protocol | Standard | Purpose |
|----------|----------|---------|
| HTTP | RFC 9110/9113 | REST API |
| WebSocket | RFC 6455 | Realtime |
| SSE | HTML Standard | Streaming |
| Error format | RFC 9457 | Problem Details |

---

## 13. Backwards Compatibility

**Version 1.0 → 3.0 migration:**

Phase 1 replaces MVP terminology. Core functionality remains.

**Migration path:**
- Phase 1 is now the minimum service path
- No breaking changes to core API contracts
- Error format updated to RFC 9457 (backwards compatible wrapper available)

---

## 14. Approval

| Role | Name | Date |
|------|------|------|
| Product | | |
| Engineering | | |
| Security | | |
| Leadership | |

---

*Document owner: Product Team*  
*Last updated: 2026-04-17*  
*Version: 3.0 (Production-Ready)*
