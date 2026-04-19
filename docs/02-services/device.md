# Device / Environment / Ambient Service - Technical Specification

> **For:** Engineering  
> **Status:** Partial-Active (v3.1) — DeviceService and EnvironmentService implemented; Mobile Bridge pending
> **Version:** 3.1  
> **Reference:** Butler cross-device, ambient, wearable, health, media, and environment control plane  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **DeviceService** | ✅ IMPLEMENTED | Registry, pairing, state fetch, command dispatch, caching |
| 2 | **AdapterRegistry** | ✅ IMPLEMENTED | Protocol resolver (Matter/HTTP/MQTT/BLE) |
| 3 | **DevicePolicy** | ✅ IMPLEMENTED | Trust and permission gate for dispatch |
| 4 | **CapabilityValidator** | ✅ IMPLEMENTED | Schema-driven action validation |
| 5 | **EnvironmentService** | ✅ IMPLEMENTED | Ambient context provider — temporal, location, platform, system state (v3.1) |
| 6 | **Mobile Bridge** | 🔲 PLANNED | iOS/Android OS intent bridge (Phase 3 roadmap) |
| 7 | **Wearable Connectors** | 🔲 PLANNED | Apple Health / Google Fit ingestion |
| 8 | **Camera/Sensor Ingress** | 🔲 PLANNED | Local camera stream access |

---

## 0.1 v3.1 Implementation Notes

> **Completed in v3.1 (2026-04-19)**

### EnvironmentService (`services/device/environment.py`) — NEW
Provides a lightweight ambient `EnvironmentSnapshot` without making OS calls or violating sovereignty:
- **Temporal context**: UTC + local ISO, timezone-aware period-of-day (morning/afternoon/evening/night), weekday, week of year
- **Location context**: Client-pushed lat/lon + city/country. Never geocoded server-side without explicit push from client.
- **Platform context**: OS (ios/android/macos/web), app version, locale, device model
- **System state**: Battery %, charging status, connectivity (wifi/cellular/offline), silent mode
- **Redis caching**: 60-second TTL per `account_id:device_id` key pair
- **Prompt injection**: `snapshot.to_prompt_block()` produces a compact `[Environment]` block for system prompt grounding

### Orchestrator Integration
`EnvironmentService` is wired into `IntakeProcessor` via `deps.py`. On every request:
1. `IntakeProcessor.process()` calls `env_service.get_snapshot()`
2. Returns `environment_block` field in `IntakeResult`
3. Orchestrator can inject this into the system prompt context

> **Fault-tolerance**: If `EnvironmentService` raises any exception, intake continues normally — `environment_block` is `None`.

### Bug Fixed
`DeviceService` previously imported from `core.deps` (FastAPI dependency injection), causing a deep circular import chain. Fixed by removing the import and passing `Redis`/`AsyncSession` as plain constructor arguments.

### Key Files
| File | Role |
|------|------|
| `services/device/environment.py` | `EnvironmentService` **[NEW v3.1]** |
| `services/device/service.py` | Device registry and command dispatch |
| `services/device/adapters.py` | Protocol adapter registry |
| `services/device/policy.py` | Trust/permission policy evaluator |
| `services/device/capabilities.py` | Capability schema validator |

---

### 1.1 Purpose
The Device / Environment / Ambient service is Butler's bridge to the physical and personal-device world. It manages device identity, pairing, capabilities, live state, presence and ambient context, health/wearable connectors, media and control surfaces, automation execution, camera and sensor ingress, and privacy-aware ambient capture.

This is not just a smart-home adapter. It is Butler's **personal device, environment, and ambient computing control plane**.

### 1.2 Responsibilities
- device identity, pairing, and ownership
- capability registry for personal devices and smart-environment devices
- protocol adapter integration (Matter, Zigbee, Z-Wave, MQTT, BLE, local APIs)
- state sync for personal devices, smart-home devices, and ambient sensors
- presence and context signal ingestion
- automation and scene runtime for physical/device actions
- media surface discovery and control
- camera stream access, snapshots, clip extraction, and motion events
- health connector ingestion from wearable/mobile ecosystems
- edge/local execution and offline fallback for trusted local actions
- ambient capture controls with privacy-first retention boundaries
- event emission to Orchestrator, Memory, ML/profile, and notifications

### 1.3 Boundaries

**Service owns:**
- device identity and trust state
- pairing and ownership
- capability registry
- live device state and ambient telemetry ingest
- health/device signal normalization
- physical/device automation runtime
- media/control adapter execution
- camera/sensor ingress metadata and access control
- event emission to Orchestrator and Memory

**Service does NOT own:**
- long-term historical analytics
- final health interpretation
- user profile inference
- recommendation logic
- vision inference itself
- primary long-term memory retention policy
- auth source of truth
- unlimited raw surveillance retention

### 1.4 Adjacent Service Separation

| Adjacent service | Separation |
|---|---|
| Auth | Auth owns user/account identity; Device owns device identity and trust state |
| Orchestrator | Orchestrator decides what to do; Device executes device/environment actions and reports results |
| Memory | Memory stores long-term summaries/episodes; Device emits normalized events and bounded raw refs |
| ML | ML infers and recommends; Device only provides signals and control surfaces |
| Vision | Vision performs camera/image inference; Device manages stream access, camera metadata, and event hooks |
| Security | Security defines policy classes and enforcement logic; Device classifies physical actions and submits them through policy gates |

---

## 2. Architecture

### 2.1 Internal Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│              Device / Ambient / IoT Service                     │
├──────────────────────────────────────────────────────────────────┤
│ 1. Device Registry & Identity                                   │
│   - pairing                                                     │
│   - ownership                                                   │
│   - capability registry                                         │
│   - device trust state                                          │
├──────────────────────────────────────────────────────────────────┤
│ 2. Protocol Adapters                                            │
│   - Matter                                                      │
│   - Zigbee                                                      │
│   - Z-Wave                                                      │
│   - MQTT                                                        │
│   - Wi-Fi / LAN APIs                                            │
│   - Bluetooth / BLE                                             │
│   - Platform connectors (Android / iOS / macOS / Windows / TV) │
├──────────────────────────────────────────────────────────────────┤
│ 3. State & Telemetry Layer                                      │
│   - device state sync                                           │
│   - sensor ingest                                               │
│   - health connector ingest                                     │
│   - presence / location events                                  │
├──────────────────────────────────────────────────────────────────┤
│ 4. Automation Runtime                                           │
│   - trigger engine                                              │
│   - scene engine                                                │
│   - schedules                                                   │
│   - policy / safety checks                                      │
│   - approval hooks                                              │
├──────────────────────────────────────────────────────────────────┤
│ 5. Media & Ambient Capture                                      │
│   - camera streams                                              │
│   - snapshots / clips                                           │
│   - ambient recorder                                            │
│   - TV / speaker / media control                                │
├──────────────────────────────────────────────────────────────────┤
│ 6. Edge Runtime                                                 │
│   - local command execution                                     │
│   - offline fallback                                            │
│   - local cache / state                                         │
├──────────────────────────────────────────────────────────────────┤
│ 7. Event Bridge                                                 │
│   - memory write events                                         │
│   - orchestrator events                                         │
│   - notifications                                               │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Auth | Internal | user/account binding for device ownership |
| Orchestrator | Internal | command requests, context-driven routing |
| Memory | Internal | episodic summary writes and signal export |
| ML | Internal | optional enrichment consumers, not primary control loop |
| Vision | Internal | camera/image inference and anomaly analysis |
| Security | Internal | safety classes, approval gates, policy enforcement |
| PostgreSQL | External | device registry, capabilities, automation definitions |
| Redis | External | hot device state cache, trigger state, presence cache |
| Object storage | External | clip/snapshot refs and bounded raw capture retention |

---

## 3. Device Model

### 3.1 Capability-Based Design

Every device is modeled by capabilities, not just broad marketing categories.

```python
class DeviceCapability(str, Enum):
    POWER = "power"
    DIMMING = "dimming"
    COLOR = "color"
    TEMPERATURE_SETPOINT = "temperature_setpoint"
    LOCK = "lock"
    UNLOCK = "unlock"
    MOTION = "motion"
    PRESENCE = "presence"
    CAMERA_STREAM = "camera_stream"
    SNAPSHOT = "snapshot"
    RECORD = "record"
    AUDIO_OUTPUT = "audio_output"
    DISPLAY_MEDIA = "display_media"
    VOLUME = "volume"
    STEP_COUNT = "step_count"
    HEART_RATE = "heart_rate"
    SLEEP = "sleep"
    WORKOUT = "workout"
    SCREEN_STATE = "screen_state"
    BATTERY = "battery"
```

### 3.2 Device Classes

Supported domains include:
- phones and tablets
- watches and wearables
- laptops and desktops
- TVs, streamers, and smart displays
- earbuds, headphones, and speakers
- lighting, climate, locks, plugs, blinds
- sensors, cameras, alarms, and power monitors
- appliances and robot vacuums

### 3.3 Registry Fields

```json
{
  "device_id": "dev_123",
  "owner_id": "usr_123",
  "household_id": "home_456",
  "protocol": "matter",
  "vendor": "Google",
  "model": "Nest Cam",
  "firmware_version": "1.2.3",
  "capabilities": ["camera_stream", "snapshot", "motion"],
  "trust_state": "trusted",
  "online_state": "online",
  "room": "living_room",
  "tags": ["camera", "entryway"],
  "last_seen_at": "2026-04-18T12:00:00Z"
}
```

### 3.4 Personal Device Registry

Track for personal devices:
- platform
- companion app/runtime version
- notification token
- auth/session binding
- active account context
- sensor availability
- local runtime availability

---

## 4. Protocol and Platform Strategy

### 4.1 Protocol Adapters

```yaml
protocols:
  - matter
  - zigbee
  - z_wave
  - mqtt
  - wifi_lan_api
  - bluetooth_ble
```

### 4.2 Platform Connectors [UNIMPLEMENTED]

```yaml
platform_connectors:
  - android_companion [UNIMPLEMENTED]
  - ios_companion [UNIMPLEMENTED]
  - macos_helper [UNIMPLEMENTED]
  - windows_helper [UNIMPLEMENTED]
  - linux_helper [UNIMPLEMENTED]
  - tv_media_adapter [UNIMPLEMENTED]
  - health_connect [UNIMPLEMENTED]
  - healthkit [UNIMPLEMENTED]
```

### 4.3 Integration Principle
- prefer unified modern protocols when available
- use bridge/adaptor patterns for fragmented ecosystems
- keep protocol lifecycle inside adapters, not in Orchestrator
- normalize everything into Butler device/capability/event contracts

---

## 5. State, Presence, and Context

### 5.1 Live State Model

```python
class DeviceStateService:
    async def get_state(self, device_id: str) -> dict:
        cached = await self.redis.get(f"device:{device_id}:state")
        if cached:
            return json.loads(cached)

        state = await self.adapter_registry.get(device_id).fetch_state()
        await self.redis.setex(f"device:{device_id}:state", 60, json.dumps(state))
        return state

    async def set_state(self, device_id: str, desired_state: dict):
        await self.policy_gate.validate_command(device_id, desired_state)
        await self.adapter_registry.get(device_id).apply_state(desired_state)
```

### 5.2 Presence Signals
- home / away
- room presence
- active device
- active media surface
- on-body wearable hint
- sleep-state hint
- focus / work mode hint
- later: driving / car context

### 5.3 Butler Use
This lets Butler choose:
- watch vs phone vs TV vs speaker as response surface
- whether to speak aloud or stay silent
- when to trigger scenes or suppress notifications

---

## 6. Health Connector Layer [UNIMPLEMENTED]

### 6.1 Purpose
The service is the **connector and normalized ingest plane** [UNIMPLEMENTED] for health and wearable signals. It is not the long-term health reasoning brain.

### 6.2 Sources
- Android Health Connect
- Apple HealthKit
- optional vendor APIs later (Fitbit, Garmin, Oura, etc.)

### 6.3 Supported Metrics
- steps
- sleep
- heart rate
- resting heart rate
- HRV when available
- workouts
- calories
- body metrics
- tightly consented medical data only under stronger controls

### 6.4 Normalized Event Schema

```json
{
  "source": "health_connect|healthkit",
  "user_id": "usr_123",
  "device_id": "dev_watch_1",
  "metric": "heart_rate|sleep|steps|workout",
  "value": 72,
  "unit": "bpm",
  "observed_at": "2026-04-18T12:00:00Z",
  "confidence": 0.95,
  "raw_ref": "evt_abc"
}
```

### 6.5 Boundary
Health signals are forwarded to Memory / ML-profile consumers as normalized events. They do not directly become automation decisions without explicit policy and user consent.

---

## 7. Automation Runtime

### 7.1 Runtime Model

```python
@dataclass
class AutomationRule:
    id: str
    name: str
    enabled: bool
    triggers: list[Trigger]
    conditions: list[Condition]
    actions: list[Action]
    cooldown_s: int
    requires_approval: bool
    safety_class: str  # safe_auto | confirm | restricted
```

### 7.2 Runtime Capabilities
- trigger graph
- condition evaluation
- approval gates
- idempotency
- concurrency control
- deadman timers
- retries
- cooldowns
- simulation mode
- audit trail

### 7.3 Example Trigger Types

```yaml
trigger_types:
  time_based: "At specific times"
  device_state: "When device changes state"
  location: "When user enters/exits location"
  sensor_value: "When sensor crosses threshold"
  presence: "When room/user presence changes"
  wearable_state: "When health/wearable condition changes"
  voice_command: "Voice command triggered"
```

### 7.4 Example Action Types

```yaml
action_types:
  device_control: "Change device state"
  scene: "Activate scene"
  notification: "Send notification"
  media_control: "Play/pause/cast/volume"
  camera_control: "Snapshot/record toggle"
  delay: "Wait X seconds"
  condition: "If/else logic"
```

---

## 8. Media, Cameras, and Ambient Capture

### 8.1 Media Surfaces
Support should include:
- TVs and smart displays
- streamers / casting endpoints
- speakers and audio endpoints
- volume, play/pause, active media metadata
- later overlay/presentation surfaces where appropriate

### 8.2 Camera Support

The service manages:
- stream access
- snapshot and clip extraction
- motion events
- metadata, privacy zones, and retention refs

Vision service manages:
- object/person detection
- anomaly analysis
- higher-order image interpretation

### 8.3 Camera Interfaces

```python
class CameraService:
    async def get_stream(self, camera_id: str) -> dict:
        return {"stream_url": f"hls://camera/{camera_id}/index.m3u8"}

    async def get_snapshot(self, camera_id: str) -> bytes:
        return await self.camera_adapter(camera_id).capture()

    async def record_clip(self, camera_id: str, duration_s: int = 60):
        return await self.camera_adapter(camera_id).record(duration_s)
```

### 8.4 Ambient Recorder

Inputs may include:
- mic snippets / voice activity events
- camera motion clips
- screen snapshots or screen-event summaries
- wearable sensor intervals
- device usage events
- room presence events

Modes:
- off
- manual
- scheduled
- context-triggered
- emergency
- local-only
- local + summarized cloud sync

Policies:
- explicit opt-in
- per-source toggle
- local-first buffering where possible
- rolling retention
- summarize/redact before memory persistence
- visible recording indicator where applicable
- emergency stop / kill switch

Raw always-on data should **not** flow directly into long-term memory by default.

---

## 9. Security and Safety Model

### 9.1 Safety Classes

| Class | Examples |
|---|---|
| `safe_auto` | light dimming, small thermostat adjustments |
| `confirm` | door unlock, alarm disarm, recorder enable |
| `restricted` | destructive or privacy-sensitive actions |

### 9.2 Rules
- per-device permission model
- high-risk actions require approval
- local network trust does not equal user trust
- signed command envelopes for companion apps
- full audit trail for all side effects
- lock, door, camera, and mic actions are sensitive by default

---

## 10. API Contracts

### 10.1 Device Registry and Control

```yaml
GET  /devices
GET  /devices/{device_id}
POST /devices/discover
POST /devices/{device_id}/pair
POST /devices/{device_id}/unpair
GET  /devices/{device_id}/capabilities
GET  /devices/{device_id}/state
POST /devices/{device_id}/commands
```

### 10.2 Presence

```yaml
GET /presence
GET /presence/devices
GET /presence/rooms
```

### 10.3 Health

```yaml
GET  /health/sources
POST /health/sources/connect
GET  /health/metrics
POST /health/sync
```

### 10.4 Media

```yaml
GET  /media/surfaces
POST /media/surfaces/{id}/play
POST /media/surfaces/{id}/pause
POST /media/surfaces/{id}/cast
```

### 10.5 Cameras

```yaml
GET  /cameras
GET  /cameras/{camera_id}/stream
GET  /cameras/{camera_id}/snapshot
GET  /cameras/{camera_id}/events
POST /cameras/{camera_id}/record
```

### 10.6 Automation

```yaml
GET  /automations
POST /automations
POST /automations/{id}/enable
POST /automations/{id}/disable
POST /automations/{id}/simulate
POST /automations/{id}/run
```

### 10.7 Ambient Capture

```yaml
GET  /ambient/recorders
POST /ambient/recorders/start
POST /ambient/recorders/stop
GET  /ambient/events
```

---

## 11. Performance Model

| Class | Target |
|------|--------|
| local device control ack | <300ms |
| hot state reads | <100ms from cache |
| camera snapshot | <1s typical |
| local safe automation trigger-to-action | <500ms |
| health sync | asynchronous; freshness over latency |

---

## 12. Observability

Track:
- device online/offline transitions
- command success/failure by adapter
- automation trigger and action latency
- approval-gated physical actions
- ambient capture start/stop and retention events
- health sync freshness and failures
- media surface control results

---

## 13. Testing Strategy

Required tests should cover:
- capability-based command routing
- protocol adapter fallback behavior
- personal-device and smart-home pairing flows
- automation idempotency and cooldowns
- approval-gated sensitive actions
- ambient recorder privacy controls
- camera event flow to Vision hooks
- health source permission and sync flows
- presence-driven response-surface selection inputs

---

*Document owner: Device / Environment Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Implementation-ready)*
