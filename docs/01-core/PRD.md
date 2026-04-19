# PRD - Product Requirements Document

> **For:** Product, Engineering
> **Status:** v0.3 (Production-Ready)
> **Version:** 3.0
> **Reference:** Corrected specification with boundary fixes, production targets

---

## 1. Overview

This document specifies the product requirements for **Butler** - an AI-powered personal assistant that executes tasks autonomously.

This document specifies requirements for Butler v0.3 production release.

---

## 2. User Stories

### 2.1 Core User Stories

| ID | Story | Priority |
|----|-------|----------|
| US-001 | As a user, I want to send messages via voice/text so I can communicate without opening apps | P0 |
| US-002 | As a user, I want to search the web so I can get answers instantly | P0 |
| US-003 | As a user, I want to set reminders so I never forget important tasks | P0 |
| US-004 | As a user, I want Butler to remember my preferences so I don't repeat myself | P0 |
| US-005 | As a user, I want to ask questions and get accurate answers so I don't need to search | P0 |
| US-006 | As a user, I want voice input so I can use Butler hands-free | P1 |
| US-007 | As a user, I want automated workflows so I can chain multiple actions | P1 |
| US-008 | As a user, I want recommendations so Butler can suggest actions before I ask | P2 |
| US-009 | As a user, I want Butler to predict my next action so I can confirm and move on | P2 |
| US-010 | As a user, I want voice responses so I can listen instead of reading | P2 |

---

## 3. Functional Requirements

### 3.1 Messaging (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-MSG-001 | Send SMS | User can send SMS to contacts in address book |
| FR-MSG-002 | Send WhatsApp | User can send WhatsApp messages |
| FR-MSG-003 | Contact lookup | System automatically finds contact by name |

### 3.2 Search (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-SRH-001 | Web search | User can search web via natural language |
| FR-SRH-002 | Source citation | Results include source links |
| FR-SRH-003 | Semantic search | Uses RAG for accurate answers |

### 3.3 Reminders (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-REM-001 | Set reminder | User can set time-based reminders |
| FR-REM-002 | Location reminder | User can set location-based reminders |
| FR-REM-003 | Recurring | User can set repeating reminders |

### 3.4 Memory (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-MEM-001 | Preference memory | System remembers user preferences |
| FR-MEM-002 | Context recall | System recalls conversation context |
| FR-MEM-003 | Preference inference | System learns preferences from behavior |

### 3.5 Q&A (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-QA-001 | Factual answers | System answers factual questions |
| FR-QA-002 | Context-aware | Answers consider user's context |
| FR-QA-003 | Confidence scoring | System shows confidence level |

### 3.6 Voice (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-VOC-001 | Voice input | User can speak input |
| FR-VOC-002 | Voice output | System can speak responses |
| FR-VOC-003 | Wake word | System responds to wake word |

### 3.7 Automation (P1)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-AUT-001 | Workflow creation | User can create multi-step workflows |
| FR-AUT-002 | Workflow execution | System executes saved workflows |
| FR-AUT-003 | Workflow templates | Pre-built templates available |

### 3.8 Recommendations (P2)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-REC-001 | Action suggestions | System suggests next actions |
| FR-REC-002 | Personalized | Suggestions based on user history |
| FR-REC-003 | Proactive | System suggests without prompting |

### 3.9 Prediction (P2)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-PRE-001 | Next action | System predicts next intended action |
| FR-PRE-002 | One-click execution | User can confirm and execute in one tap |

---

## 4. Non-Functional Requirements

### 4.1 Performance

| Requirement | Target |
|-------------|--------|
| Response time (simple) | <500ms |
| Response time (complex) | <3s |
| Voice latency | <1s |
| Task completion | >85% |

### 4.2 Availability

| Requirement | Target |
|-------------|--------|
| Uptime | 99.9% |
| Planned maintenance | <4h/month |
| Recovery time | <15min |

### 4.3 Scalability

| Requirement | Target |
|-------------|--------|
| Concurrent users | 50K |
| Peak RPS | 10K |
| Session capacity | 100K |

### 4.4 Security

| Requirement | Target |
|-------------|--------|
| Data encryption | E2E for sensitive data |
| Auth | JWT + biometric |
| Privacy | Local-first option |

### 4.5 Accessibility

| Requirement | Target |
|-------------|--------|
| Voice-first | Full voice interface |
| Offline mode | Core features work offline |
| Low bandwidth | Works on 2G |

---

## 5. User Interface

### 5.1 Mobile App Screens

| Screen | Description |
|--------|-------------|
| Home | Main chat interface |
| Memory | User preferences view |
| Workflows | Automation list |
| Settings | App configuration |

### 5.2 Interaction Patterns

| Pattern | Description |
|---------|-------------|
| Chat | Primary input method |
| Voice | Hands-free input |
| Quick actions | One-tap shortcuts |
| Suggestions | Proactive cards |

---

## 6. Data Requirements

### 6.1 User Data

| Data | Storage | Purpose |
|------|---------|---------|
| Profile | Encrypted | User identity |
| Contacts | Encrypted | Messaging |
| Preferences | Encrypted | Personalization |
| History | Encrypted | Context |

### 6.2 Usage Data

| Data | Storage | Purpose |
|------|---------|---------|
| Conversations | Logged (opt-in) | ML training |
| Actions | Logged | Pattern learning |
| Feedback | Logged | Improvement |

---

## 7. Third-Party Integrations

### 7.1 Phase 1 Integrations

| Integration | Purpose | Status |
|------------|---------|--------|
| Twilio | SMS | Required |
| WhatsApp Business | Messaging | Required |
| OpenAI | LLM | Required |
| Neo4j | Graph memory | Required |
| Qdrant | Vector search | Required |

### 7.2 Future Integrations

| Integration | Purpose |
|-------------|---------|
| Google Calendar | Scheduling |
| Gmail | Email |
| Stripe | Payments |
| Uber Eats | Food ordering |
| Spotify | Music |

---

## 8. Edge Cases

| Scenario | Handling |
|----------|----------|
| No internet | Show offline mode, queue actions |
| API failure | Retry 3x, then graceful failure |
| Wrong intent | Ask for clarification |
| Ambiguous request | Offer options |
| Permission denied | Guide to settings |

---

## 9. Success Criteria

| Metric | Target |
|--------|--------|
| Task completion rate | >85% |
| User satisfaction | >4.0 stars |
| First response time | <500ms |
| Error rate | <1% |

---

## 10. Out of Scope

- Physical delivery/robots
- Financial transactions (directly)
- Medical/legal advice
- Hardware control
- Enterprise SSO (V1)

---

## 11. Performance Requirements

### 11.1 Response Time Targets (P50/P95/P99)

| Request Type | P50 | P95 | P99 |
|--------------|-----|-----|-----|
| Simple (intent) | 100ms | 200ms | 500ms |
| Medium (RAG) | 500ms | 1s | 2s |
| Complex (LLM) | 1s | 2s | 3s |
| Voice latency | <1s | <1.5s | <2s |

### 11.2 Scalability Targets

| Requirement | Target |
|-------------|--------|
| Concurrent users | 50K-100K |
| Peak RPS | 10K |
| Session capacity | 100K |

### 11.3 Availability

| Requirement | Target |
|-------------|--------|
| Uptime | 99.9% |
| Planned maintenance | <4h/month |
| Recovery time | <15min |

---

## 12. Protocol Standards

| Protocol | Standard | Implementation |
|----------|----------|----------------|
| HTTP | RFC 9110/9113 | REST API |
| WebSocket | RFC 6455 | Realtime |
| SSE | HTML Standard | Streaming |
| Error format | RFC 9457 | Problem Details |

---

## 13. Error Response Standards (RFC 9457)

All error responses MUST follow RFC 9457 Problem Details format:

```json
{
  "type": "https://docs.butler.lasmoid.ai/problems/{error-type}",
  "title": "Error Title",
  "status": {http_code},
  "detail": "Human-readable description",
  "instance": "/api/v1/endpoint#req_xxx"
}
```

---

## 14. Backwards Compatibility

**Version 1.0 → 3.0 changes:**

- Phase 1 replaces MVP terminology
- Error format migrated to RFC 9457 Problem Details
- No breaking changes to core functionality

**Migration path:**
1. Update error handling to RFC 9457 format
2. Phase 1 features are the minimum service path

---

*Document owner: Product Team*  
*Last updated: 2026-04-17*  
*Version: 3.0 (Production-Ready)*
