# Event Contract

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Event Schema

All events MUST follow this schema:

```typescript
interface ButlerEvent {
  eventId: UUID;
  eventType: string;           // Fully qualified type
  timestamp: ISO8601;
  userId?: UUID;
  sessionId?: UUID;
  traceId: UUID;
  spanId?: string;
  data: JSON;
  metadata?: JSON;
}
```

---

## 2. Event Categories

### 2.1 User Events

| EventType | Direction | Description |
|-----------|-----------|-------------|
| user.message.received | ↑ | User sent message |
| user.message.response | ↓ | Butler responded |
| user.voice.input | ↑ | Voice transcript |
| user.voice.output | ↓ | Synthesized speech |
| user.session.start | ↑ | Session began |
| user.session.end | ↑ | Session ended |
| user.action.request | ↑ | Action requested |
| user.action.approved | ↑ | Action approved |
| user.action.denied | ↑ | Action denied |

### 2.2 Intent Events

| EventType | Direction | Description |
|---------|-----------|-------------|
| intent.classified | ↑ | Intent detected |
| intent.confidence.low | ↑ | Low confidence |
| intent.ambiguous | ↑ | Ambiguous input |

### 2.3 Execution Events

| EventType | Direction | Description |
|---------|-----------|-------------|
| task.started | ↑ | Task started |
| task.step.started | ↑ | Step started |
| task.step.completed | ↑ | Step completed |
| task.completed | ↑ | Task completed |
| task.failed | ↑ | Task failed |
| tool.executing | ↑ | Tool executing |
| tool.executed | ↑ | Tool completed |
| tool.failed | ↑ | Tool failed |
| tool.rate-limited | ↑ | Rate limited |

### 2.4 Memory Events

| EventType | Direction | Description |
|---------|-----------|-------------|
| memory.stored | ↑ | Memory stored |
| memory.retrieved | ↑ | Memory retrieved |
| memory.updated | ↑ | Memory updated |
| memory.deleted | ↑ | Memory deleted |

### 2.5 Approval Events

| EventType | Direction | Description |
|---------|-----------|-------------|
| approval.requested | ↑ | Approval requested |
| approval.granted | ↑ | Approval granted |
| approval.denied | ↑ | Approval denied |
| approval.expired | ↑ | Approval timed out |

### 2.6 Session Events

| EventType | Direction | Description |
|---------|-----------|-------------|
| session.safeguard.triggered | ↑ | Safety triggered |
| session.capability.changed | ↑ | Capability changed |
| session.assurance.elevated | ↑ | Assurance elevated |

---

## 3. Delivery Classes

### Class A: Guaranteed

- Stored to durability before acknowledgment
- Exactly-once processing
- Consumer group offset tracking
- Use: Task state, approvals

### Class B: At-Least-Once

- Acknowledged on send
- May duplicate
- Consumer idempotency required
- Use: Analytics, metrics

### Class C: Fire-And-Forget

- No acknowledgment
- Best effort
- Use: Real-time presence, typing indicators

---

## 4. Event Versioning

```
EventType: {domain}.{entity}.{action}.v{version}

Example: task.completed.v2
```

Version migration:
- Add new version alongside old
- Deprecate old after 2 releases
- Remove deprecated after migration window

---

## 5. Payload Examples

### Task Started Event

```json
{
  "eventId": "evt_abc123",
  "eventType": "task.started.v1",
  "timestamp": "2026-04-18T10:30:00Z",
  "userId": "usr_xyz",
  "sessionId": "ses_abc",
  "traceId": "trc_123",
  "data": {
    "taskId": "tsk_001",
    "intent": "send_message",
    "safetyClass": "confirm"
  }
}
```

### Memory Stored Event

```json
{
  "eventId": "evt_def456",
  "eventType": "memory.stored.v1",
  "timestamp": "2026-04-18T10:30:01Z",
  "userId": "usr_xyz",
  "traceId": "trc_123",
  "data": {
    "memoryId": "mem_001",
    "type": "preference",
    "importance": 8
  }
}
```

---

## 6. Schema Registry

Events are registered in `schemas/events/` with:
- JSON Schema definition
- Example payloads
- Migration guide

---

*Event contract owner: Architecture Team*
*Version: 4.0*