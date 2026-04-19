# Realtime Service - Technical Specification

> **For:** Engineering  
> **Status:** Active (v3.1) — Stream delivery, Redis replay, and WebSocket fan-out implemented; multi-device routing partial
> **Version:** 3.1  
> **Reference:** Butler realtime delivery, typed event streaming, resumable sessions, and multi-device coordination  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **ButlerStreamDispatcher** | ✅ IMPLEMENTED | ButlerEvent → Redis Stream XADD + WebSocket fan-out |
| 2 | **SSE Replay** | ✅ IMPLEMENTED | Cursor-based XRANGE replay over Redis Stream (48h TTL) |
| 3 | **ConnectionManager** | ✅ IMPLEMENTED | WebSocket lifecycle, session binding, broadcast |
| 4 | **Presence** | ✅ IMPLEMENTED | Redis-backed activity signals with TTL |
| 5 | **Event Schema** | ✅ IMPLEMENTED | Typed `RealtimeEvent` vocabulary with durable/ephemeral flag |
| 6 | **Multi-Device Routing** | ⚪ PARTIAL | Account-level fan-out works; per-device preference routing not yet implemented |

---

## 0.1 v3.1 Notes

> **Current state as of 2026-04-19**

### ButlerStreamDispatcher (`services/realtime/stream_dispatcher.py`) — Production
`ButlerStreamDispatcher` is the central routing hub:
- **Receives**: `ButlerEvent` objects from `OrchestratorService.intake_streaming()`
- **Maps**: Internal event types to `RealtimeEvent` vocabulary (stream.token, workflow.complete, tool.call, approval.request, error)
- **Persists**: Durable events to `butler:events:{account_id}` Redis Stream (`XADD`, `MAXLEN=1000`)
- **Fan-out**: Broadcasts to connected WebSocket clients via `ConnectionManager`
- **Replay**: `sse_replay_stream()` reads from stream with XRANGE cursor; signals `replay.complete` at end
- **Resilience**: WS send failures are `debug`-logged and swallowed — stream persistence failures are `warning`-logged but never propagate

### Stream design
| Property | Value |
|----------|-------|
| Stream key | `butler:events:{account_id}` |
| Max entries | 1000 (approximate trim) |
| TTL | 48 hours (sliding, refreshed on every write) |
| Cursor | Redis stream entry ID; `0` = replay all, `$` = live tail |

### ConnectionManager (`services/realtime/manager.py`)
- Session ↔ WebSocket mapping (in-memory)
- `send_event(account_id, event)` broadcasts to all sockets for an account
- Disconnect is graceful — connections removed on close

### Presence (`services/realtime/presence.py`)
- `PresenceManager` tracks per-account activity with Redis keys (`butler:presence:{account_id}`)
- TTL-based expiry signals disconnect automatically

### What is NOT yet implemented
- **Per-device routing**: when a user has multiple devices, events always fan-out to all — target-device filters not applied
- **Group/shared session delivery**: household / shared account event routing
- **Backpressure control**: no consumer-side slow-subscriber detection yet

### Key Files
| File | Role |
|------|------|
| `services/realtime/stream_dispatcher.py` | `ButlerStreamDispatcher` — Redis Streams + WS fan-out |
| `services/realtime/manager.py` | `ConnectionManager` — WebSocket lifecycle |
| `services/realtime/presence.py` | `PresenceManager` — activity signals |
| `services/realtime/events.py` | `RealtimeEvent` schema + `Events` factory |
| `services/realtime/routes.py` | WebSocket + SSE FastAPI routes |

---

## 1. Service Overview

### 1.1 Purpose
The Realtime service is Butler's **realtime delivery and session stream platform** - handling:
- Live connection lifecycle management
- Typed event streaming
- Resumable delivery with replay
- Presence signaling
- Multi-device session coordination
- Low-latency stream fanout
- Backpressure control

This is NOT "WebSocket service." This is a delivery runtime for Butler's live sessions, workflows, approvals, and notifications.

### 1.2 Responsibilities

| Responsibility | Description |
|--------------|-------------|
| Connection Gateway | WebSocket + SSE connection lifecycle |
| Session Binding | Auth ticket → session/account/device mapping |
| Stream Multiplexing | Multiple streams per connection |
| Delivery Engine | Ephemeral + durable delivery classes |
| Presence Engine | User/device presence signals |
| Replay/Resume Engine | Reconnect replay, cursor management |
| Backpressure Control | Flow control, queue limits, drop policies |

### 1.3 Boundaries

| Service | Separation |
|---------|-----------|
| Gateway | Gateway owns HTTP. Realtime owns WebSocket/SSE. |
| Auth | Auth mints connection tickets. Realtime validates and binds sessions. |
| Orchestrator | Orchestrator publishes workflow events. Realtime delivers them. |
| Memory | Memory subscribes to memory-write events. Realtime delivers them. |
| Notification | Notifications published to Realtime. Realtime delivers to devices. |

**Service does NOT own:**
- HTTP transport (Gateway)
- Credential source of truth (Auth)
- Message processing logic (Orchestrator)
- Long-term storage (Memory)

### 1.4 Hermes Library Integration
Realtime is a **secondary consumer** of Hermes gateway compatibility code.

Useful Hermes inputs:
- `backend/integrations/hermes/gateway/stream_consumer.py`
- `backend/integrations/hermes/gateway/session.py`
- `backend/integrations/hermes/gateway/session_context.py`

These help with streaming patterns, but Realtime owns live connection management, event contracts, and delivery semantics.

See `docs/services/hermes-library-map.md` for full mapping.

---

## 2. Architecture

### 2.1 Platform Architecture

```
                              Clients
                    ┌──────────┬──────────┬──────────┐
                    │ Mobile   │ Web      │ Watch    │
                    └──────────┴──────────┴──────────┘
                                 ↓
                    ┌─────────────────────────────┐
                    │   Connection Gateway      │
                    │  - WebSocket upgrade   │
                    │  - SSE endpoint      │
                    │  - Ticket validation│
                    └─────────────────────────────┘
                                 ↓
                    ┌─────────────────────────────┐
                    │   Session Binder         │
                    │  - Session ownership  │
                    │  - Device binding    │
                    │  - Activity state  │
                    └──────────────────���──────────┘
                                 ↓
            ┌───────────────────┼───────────────────┐
            ↓                   ↓                   ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Stream           │ │ Delivery Engine │ │ Presence Engine │
│ Multiplexer      │ │ - Durable      │ │ - Connected    │
│ - task stream    │ │ - Ephemeral   │ │ - Idle        │
│ - chat stream   │ │ - Critical    │ │ - Active dev  │
│ - notification │ │ - Backpressure│ │ - Typing      │
└──────────────────┘ └──────────────────┘ └──────────────────┘
            ↓                   ↓                   ↓
┌──────────────────┐ ┌──────────────────┐
│ Replay/Resume    │ │ Delivery Bus     │
│ Engine         │ │ - Redis Streams │
│ - last_id      │ │ - Redis Pub/Sub│
│ - replay      │ │   (ephemeral) │
│ - cursor      │ │
└──────────────────┘ └──────────────────┘
```

### 2.2 Delivery Bus Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Delivery Bus Separation                  │
├─────────────────────────────────────────────────────┤
│                                                          │
│  Class A: EPHEMERAL (Pub/Sub)                            │
│  - typing indicators                                      │
│  - presence pings                                     │
│  - transient progress hints                            │
│  - noncritical UI hints                               │
│                                                          │
│  Class B: DURABLE (Redis Streams)                       │
│  - workflow status updates                              │
│  - reminder notifications                          │
│  - approval requests                                │
│  - completion events                              │
│  - tool execution results                        │
│                                                          │
│  Class C: CRITICAL-DURABLE (Streams + ACK)           │
│  - security alerts                                 │
│  - approval resolves                             │
│  - emergency notifications                     │
│                                                          │
└─────────────────────────────────────────────────────────────┘
```

**Critical insight:** Redis Pub/Sub provides at-most-once delivery only. If a subscriber disconnects or chokes, the message is lost forever. Use Pub/Sub for ephemeral hints only. Use Redis Streams for anything important.

---

## 3. Connection Management

### 3.1 Connection Flow

```python
class ConnectionManager:
    def __init__(self):
        # Local live sockets (per instance)
        self.local_connections: dict[str, WebSocket] = {}
        
        # Distributed presence index
        self.presence_index: Redis = redis
        
        # Durable event cursors
        self.event_cursors: Redis = redis
        
        # Short-lived connection ticket validator
        self.ticket_validator: TicketValidator = None
```

### 3.2 Connection Ticket Model

**NEVER use raw query tokens:** `WS /ws/chat?token=...` is lazy and leaks into logs/proxies.

**Correct pattern:**
1. Gateway/Auth mints short-lived connection ticket
2. Client connects with ticket
3. Realtime validates ticket, binds session/account/device
4. Ticket is consumed (one-time or short TTL)

```yaml
Connection Ticket:
  issued_by: "gateway"
  issued_at: "2026-04-18T12:00:00Z"
  expires_at: "2026-04-18T12:05:00Z"  # 5 min TTL
  session_id: "session_abc"
  account_id: "acc_123"
  device_id: "mobile_456"
  capabilities: ["websocket", "sse"]
  single_use: true  # or false for resumable sessions
```

### 3.3 Connection Lifecycle

```python
async def connect(websocket: WebSocket, ticket: str):
    # 1. Validate ticket
    validated = await self.ticket_validator.validate(ticket)
    
    # 2. Bind session/account/device
    session_id = validated.session_id
    account_id = validated.account_id
    device_id = validated.device_id
    
    # 3. Accept connection (protocol ping/pong)
    await websocket.accept()
    
    # 4. Register with presence
    await self.presence.set(session_id, "connected")
    
    # 5. Load last event cursor
    last_seen = await self.get_cursor(session_id)
    if last_seen:
        # 6. Replay missed durable events
        await self.replay_missed(websocket, session_id, last_seen)
```

### 3.4 Heartbeat Protocol

Use protocol-level ping/pong (RFC 6455), not app-level JSON heartbeats:

```python
HEARTBEAT_CONFIG = {
    "protocol_ping_interval": 30,  # seconds
    "protocol_pong_timeout": 10,   # seconds
    "max_retries": 3,
    "app_heartbeat_optional": true     # not primary
}
```

---

## 4. Event Streaming

### 4.1 Event Envelope Contract

Stream typed events, NOT anonymous blobs:

```json
{
  "event_id": "evt_abc123",
  "stream": "task|chat|notification|presence",
  "type": "tool.completed",
  "session_id": "session_xyz",
  "task_id": "task_789",
  "timestamp": "2026-04-18T12:00:00Z",
  "seq": 42,
  "durable": true,
  "payload": {
    "tool": "web_search",
    "result": "..."
  }
}
```

### 4.2 Event Types

| Category | Events |
|----------|--------|
| **Session** | session.bound, session.unbound, session.resumed |
| **Intent** | intent.detected |
| **Context** | context.loaded |
| **Planning** | plan.created, plan.updated |
| **Tool** | tool.started, tool.progress, tool.completed, tool.failed |
| **Approval** | approval.required, approval.granted, approval.denied |
| **Workflow** | workflow.progress, workflow.completed, workflow.failed |
| **Notification** | notification.delivered |
| **Presence** | presence.updated |
| **Error** | error |

### 4.3 Resume/Replay Semantics

**SSE (Server-Sent Events):**
- Emit `id:` on every event
- Honor `Last-Event-ID` header on reconnect

```python
async def sse_connect(request):
    last_event_id = request.headers.get("Last-Event-ID")
    
    if last_event_id:
        # Replay missed durable events
        events = await self.replay_from(last_event_id)
        for event in events:
            yield f"id: {event.id}\ndata: {json.dumps(event)}\n\n"
    
    # Switch to live mode
    async for event in self.live_stream():
        yield f"id: {event.id}\ndata: {json.dumps(event)}\n\n"
```

**WebSocket:**
- Client sends `resume_from` with last seen event ID
- Server replays missed durable events before live mode

```python
# Client → Server
{ "type": "resume", "last_seen_event_id": "evt_abc122" }

# Server → Client (replay)
{ "type": "replay_start", "count": 5 }
{ "type": "event", "event_id": "evt_abc123", ... }
{ "type": "event", "event_id": "evt_abc124", ... }
{ "type": "replay_done" }
{ "type": "live" }
```

---

## 5. Multi-Device Routing

### 5.1 Device Semantics

Butler is multi-device. Define delivery policies:

| Event Type | Delivery Policy |
|-----------|---------------|
| Chat chunks | active-device only |
| Reminders | all-active-devices |
| Approvals | phone + watch, resolve once |
| Workflow progress | active-device |
| Notifications | configurable per user |
| Security alerts | all-devices |

### 5.2 Device Selection

```python
class DeviceRouter:
    def get_targets(self, event_type: str, account_id: str, context: dict) -> list[str]:
        policies = {
            "chat_chunk": ["active-device"],
            "reminder": ["all-active"],
            "approval": ["phone", "watch"],
            "security_alert": ["all"],
            ...
        }
        
        targets = policies.get(event_type, ["active-device"])
        devices = await self.get_devices_for_account(account_id, targets)
        return devices
```

---

## 6. Backpressure Control

### 6.1 Flow Control Policies

```python
BACKPRESSURE_CONFIG = {
    "max_events_per_connection": 1000,
    "max_bytes_per_connection": 10 * 1024 * 1024,  # 10MB
    "slow_consumer_drop_ms": 5000,
    "coalesce_progress": True,  # Coalesce rapid progress events
    "event_rate_limit_per_stream": 100,  # per second
}
```

### 6.2 Slow Consumer Handling

- Hard disconnect when queue full
- Coalesce rapid progress events
- Log and metric slow consumers
- Client-side backoff guidance

---

## 7. Presence Model

### 7.1 Presence States

| State | Meaning | Duration |
|-------|---------|----------|
| connected | Active WebSocket | Real |
| idle | No interaction >5 min | 5 min |
| recently_seen | Disconnected <30 min ago | 30 min |
| active_device | Primary interaction surface | Real-time |
| active_channel | Current context (chat/task/etc) | Real-time |
| typing | User typing indicator | Transient |

### 7.2 Presence Signals

Presence should mostly be **ephemeral**, not durable product truth. Durable truth belongs in Memory.

---

## 8. Scaling Architecture

### 8.1 Redis Configuration

```yaml
redis:
  pub_sub:
    # Ephemeral only: typing, presence pings
    channels_prefix: "rt:ephemeral:"
    
  streams:
    # Durable events with consumer groups
    stream_prefix: "rt:durable:"
    max_stream_length: 100000
    
  presence:
    # Lightweight presence index
    key_prefix: "rt:presence:"
    
  cursors:
    # Event cursor per session
    key_prefix: "rt:cursor:"
```

### 8.2 Consumer Group Pattern (for Durable Events)

```python
# Create consumer group (run once per deployment)
await redis.xgroup_create(
    "rt:durable:workflow", 
    "workers", 
    id="0", 
    mkstream=True
)

# Consumer reads next unprocessed message
messages = await redis.xreadgroup(
    group="workers",
    consumer=f"worker-{self.worker_id}",
    count=10,
    block=5000,
    streams={"rt:durable:workflow": ">"}
)

# Process and acknowledge
for msg in messages:
    await self.process(msg)
    await redis.xack("rt:durable:workflow", "workers", msg.id)
```

---

## 9. API Contracts

### 9.1 Connection

```yaml
WS /ws/realtime
  Auth: Connection ticket in Bearer token
  
  Client → Server:
    { "type": "message", "content": "..." }
    { "type": "resume", "last_seen_event_id": "..." }
    { "type": "ping" }
  
  Server → Client:
    { "type": "event", "event_id": "...", "stream": "...", "type": "...", "payload": {...} }
    { "type": "error", "message": "..." }
```

### 9.2 SSE

```yaml
GET /events/{session_id}
  Headers:
    Last-Event-ID: "evt_abc123"  # Optional for replay
  Response:
    event: message
    data: {"event_id": "...", ...}
```

### 9.3 Status

```yaml
GET /realtime/status
  Response:
    { 
      "connected_users": 1250, 
      "active_sessions": 890,
      "streams": {
        "durable": { "length": 15000, "consumers": 5 },
        "ephemeral": { "channels": 12 }
      }
    }
```

### 9.4 Presence

```yaml
GET /realtime/presence/{account_id}
  Response:
    { 
      "connected": true,
      "active_device": "mobile_abc",
      "devices": [
        { "id": "mobile_abc", "state": "active", "last_seen": "..." },
        { "id": "web_xyz", "state": "idle", "last_seen": "..." }
      ]
    }
```

---

## 10. Observability

### 10.1 Metrics

| Metric | Type | Alert |
|--------|------|------|
| realtime.connections.active | gauge | |
| realtime.connections.opened_total | counter | |
| realtime.connections.closed_total | counter | |
| realtime.connection.duration_seconds | histogram | |
| realtime.outbound.events_total | counter | |
| realtime.outbound.bytes_total | counter | |
| realtime.outbound.queue_depth | gauge | >1000 |
| realtime.replay.events_total | counter | |
| realtime.resume.success_total | counter | |
| realtime.dropped_events_total | counter | >0 |
| realtime.presence.updates_total | counter | |

### 10.2 Trace Attributes

- butler.session_id
- butler.task_id
- butler.stream_type
- butler.connection_id
- butler.channel
- net.transport

---

## 11. Runbook Quick Reference

### 11.1 Connection Explosion

```bash
# Check connections
curl http://realtime:8004/realtime/status

# Check per-instance
kubectl exec -it deployment/realtime -- redis-cli PUBSUB NUMSUB rt:ephemeral:*

# Scale
kubectl scale deployment/realtime --replicas=6
```

### 11.2 Message Loss

```bash
# Check pending (unacknowledged) messages
redis-cli XPENDING rt:durable:workflow workers

# Check stream length
redis-cli XLEN rt:durable:workflow

# Reclaim stalled
redis-cli XCLAIM rt:durable:workflow workers 30000 <message-id>
```

### 11.3 Slow Consumer

```bash
# Check queue depth per connection
curl http://realtime:8004/realtime/queue_depth

# Force disconnect slow consumers
curl -X POST http://realtime:8004/realtime/force_disconnect -d '{"reason": "slow_consumer"}'
```

---

*Document owner: Realtime Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Implementation-ready)*

(End of file - total 445 lines)