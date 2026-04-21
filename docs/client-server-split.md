# Butler Client-Server Split Specification

**Principle:** Minimize latency, maximize privacy, leverage cloud for intelligence.

---

## The Split Principle

```
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION FRAMEWORK                         │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│   DATA GENERATED ON DEVICE                                   │
│   (voice, sensors, local actions)                           │
│   │                                                         │
│   ▼                                                         │
│   PROCESS WHERE IT'S GENERATED                              │
│   │                                                         │
│   ├── If privacy required    → Client side only            │
│   ├── If latency < 200ms      → Client side               │
│   └── If needs cloud data    → Hybrid                    │
│                                                              │
│   CLOUD FOR:                                                │
│   - LLM inference (heavy)                                   │
│   - Cross-device context                                    │
│   - User memory/personalization                             │
│   - Knowledge graph                                        │
│   - Recommendations                                        │
│                                                              │
│   CLIENT FOR:                                               │
│   - Wake word (always-on)                                  │
│   - VAD (always-on)                                       │
│   - Local sensors                                           │
│   - Device-specific actions                                 │
│   - Privacy-sensitive processing                           │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Complete Client-Server Map

### 1. VOICE INPUT

| Step | Client | Server | Why |
|------|--------|--------|-----|
| Microphone capture | ✅ | | Hardware access |
| Wake word detection | ✅ | | Must be always-on, <50ms |
| Voice activity detection | ✅ | | Must be always-on, <5ms |
| Audio encoding | ✅ | | Compress for传输 |
| Send to server | | ✅ | Cloud ASR |

```
CLIENT ONLY:        [Mic] → [Wake] → [VAD] → [Encode]
                        │
                        ▼ send encoded audio
SERVER:               [Decode] → [ASR] → [Text]
```

### 2. IDENTITY

| Step | Client | Server | Why |
|------|--------|--------|-----|
| Voice embedding extraction | ⚡ | ✅ | Can do both, prefer server |
| Embedding storage | | ✅ | Persistent |
| Voice match | | ✅ | Compare against enrolled |
| User profile fetch | | ✅ | Database query |
| Preferences load | | ✅ | Database query |

**Privacy Note:** Voice embedding NEVER leaves device in raw form. Only comparison result.

```
CLIENT:        [Voice] → [Embedding]
                        │ send only embedding vector (not raw audio)
SERVER:               [Match] → [Profile] → [Return]
```

### 3. CONTEXT

| Context Type | Client | Server | Why |
|--------------|--------|--------|-----|
| GPS location | ✅ | | Privacy, always local |
| WiFi/Cell location | ✅ | | Privacy, always local |
| BLE proximity | ✅ | | Local hardware |
| UWB ranging | ✅ | | Local hardware |
| Device sensors | ✅ | | Local only |
| Time/routine | ✅ | | Can calculate locally |
| Calendar | | ✅ | Cloud sync |
| Meeting status | | ✅ | Cloud sync |
| Cross-device presence | | ✅ | Needs cloud |

**Privacy:** Location never sent to server in raw form. Only inferred place (home/office) sent.

```
CLIENT SENSORS:  [GPS] → [Infer: home/office] → [Send place only]
SERVER:                     [Get other device presence]
```

### 4. INTENT

| Step | Client | Server | Why |
|------|--------|--------|-----|
| Speech-to-text | | ✅ | Needs LLM |
| Intent classification | | ✅ | Needs LLM |
| Entity extraction | | ✅ | Needs LLM |
| Slot filling | | ✅ | Needs memory |
| Context resolution | | ✅ | Needs cross-device |

**Hybrid Option:** For offline, use small local model for basic commands only.

```
SERVER:        [Text] → [LLM] → [Intent] → [Action needed]
```

### 5. ACTION EXECUTION

| Action Type | Client | Server | Why |
|-------------|--------|--------|-----|
| Local device control | ✅ | ⚡ | Matter runs locally |
| Cloud API calls | | ✅ | Can't do locally |
| Notifications | ✅ | ⚡ | Can trigger both |
| Response generation | | ✅ | Needs LLM |
| Response delivery | ✅ | | Play on local speaker |

```
SPLIT BY ACTION TYPE:

┌─────────────────────┐     ┌─────────────────────┐
│   CLIENT EXECUTES  │     │   SERVER EXECUTES  │
├─────────────────────┤     ├─────────────────────┤
│ • Turn on lights   │     │ • Search web        │
│ • Play music      │     │ • Get calendar     │
│ • Send notification│     │ • Call API         │
│ • Local playback  │     │ • Send email       │
│ • Screen display  │     │ • Database query   │
│ • Haptic feedback │     │ • LLM generation   │
└─────────────────────┘     └─────────────────────┘
```

---

## Detailed Split by Feature

### Feature: Wake Word

```
CLIENT SIDE (100%)
├── Model runs: openWakeWord
├── Microphone access
├── Detection threshold
├── Trigger signal
└── Never sends audio until triggered

SERVER: Nothing
```

### Feature: Voice Activity Detection

```
CLIENT SIDE (100%)
├── Model runs: Silero VAD
├── Continuous microphone access
├── Speech segment detection
└── Only streams to server when speech detected

SERVER: Nothing
```

### Feature: Speech-to-Text

```
CLIENT SIDE:
├── Audio capture
├── Encoding/compression
└── Send to server

SERVER SIDE:
├── Decode audio
├── Run Whisper model
├── Return text
```

### Feature: Speaker Identity

```
CLIENT SIDE:
├── Extract embedding (ECAPA-TDNN)
├── Send embedding vector (NOT raw audio)

SERVER SIDE:
├── Compare to enrolled embeddings
├── Return user_id + confidence
├── Fetch profile + preferences
```

### Feature: Location Context

```
CLIENT SIDE (Privacy):
├── GPS raw data
├── WiFi SSID
├── Cell tower
├── BLE beacons
├── Accelerometer
├── All local only!

HYBRID:
├── Client infers: home/office/car
├── Client sends: place (not GPS)
├── Server adds: other device presence
```

### Feature: Device Proximity

```
CLIENT SIDE:
├── BLE scanning
├── UWB ranging
├── WiFi RTT
├── Distance estimation
└── Send: {device_id, distance, method}

SERVER: Nothing (pure local)
```

### Feature: Intent Understanding

```
SERVER ONLY (needs LLM):
├── Text input
├── Classify: command/question/request
├── Extract entities
├── Fill slots from memory
└── Return: complete intent
```

### Feature: Smart Home Control

```
HYBRID SPLIT:

CLIENT (Local Matter):
├── Matter protocol execution
├── Device discovery
├── Direct device control
└── <10ms latency

SERVER (Orchestration):
├── What to control (decision)
├── Scene/routine logic
└── Cross-device coordination
```

### Feature: Calendar Integration

```
CLIENT:
├── Request calendar access
└── Request event data

SERVER:
├── Sync with calendar APIs
├── Process events
└── Return relevant events
```

### Feature: Music Playback

```
CLIENT:
├── Connect to speaker via WiFi/BLE
├── Decode audio stream
├── Play on local speaker

SERVER:
├── Decide what to play
├── Get audio stream source
└── Send URL to client
```

### Feature: Notifications

```
CLIENT (Delivery):
├── Push notification display
├── Haptic feedback
├── Sound alert
└── Local notification scheduling

SERVER (Trigger):
├── Decide to notify
├── Compose message
└── Route to correct channel
```

---

## Offline Mode

### What Works Offline?

| Feature | Offline | Via |
|---------|---------|-----|
| Wake word | ✅ | Local model |
| Basic commands | ✅ | Local intent classifier |
| Smart home | ✅ | Local Matter hub |
| Music playback | ✅ | Local network |
| Notifications | ✅ | Local queue |
| Voice embedding | ✅ | Local extraction |

### What Needs Cloud?

| Feature | Needs | Why |
|---------|-------|-----|
| Full ASR | Cloud | Large model |
| Intent classification | Cloud | Full LLM |
| Cross-device context | Cloud | Data elsewhere |
| Web search | Cloud | Internet |
| Calendar sync | Cloud | Cloud API |

### Offline Fallback

```
OFFLINE MODE:
├── Use small local models
├── Cache last known context
├── Queue actions for sync
└── Notify: "Working offline"
```

---

## Response Time Targets

| Step | Location | Target |
|------|----------|--------|
| Wake word detection | Client | <50ms |
| Voice activity | Client | <5ms |
| Send audio | Network | <100ms |
| ASR | Server | <500ms |
| Intent + action | Server | <1000ms |
| Response generation | Server | <1500ms |
| **Total (cloud)** | | **<2.5s** |
| | |
| Local commands | Client | <100ms |
| Smart home | Client | <50ms |

---

## Privacy Boundaries

### Never Leaves Device

| Data | Reason |
|------|--------|
| Raw microphone | Privacy |
| Raw GPS | Privacy |
| Face images | Privacy |
| BLE scan results | Privacy |
| UWB raw ranging | Privacy |

### Only Comparison Result Leaves

| Data | What Leaves |
|------|-------------|
| Voice | Embedding vector only |
| Location | Inferred place only |
| Sensors | Processed context only |

### Server Only

| Data | Where |
|------|-------|
| User profile | Server database |
| Preferences | Server database |
| Memory | Server database |
| Knowledge | Server database |

---

## Network Efficiency

### What Sends When

| Event | What Sends | Size |
|-------|-----------|------|
| Wake triggered | Nothing until speech | 0 |
| Speech starts | Encoded audio | ~10KB/s |
| Speech ends | Embedding only | ~1KB |
| Intent ready | Action request | ~500B |
| Response ready | Text + metadata | ~1KB |

### Bandwidth

| Scenario | Estimate |
|----------|----------|
| Voice only | ~10KB/s while speaking |
| Idle | ~0 (keep-alive only) |
| Monthly | ~50MB typical use |

---

## The Split Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                      BUTLER SPLIT                              │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│   CLIENT (Device)              SERVER (Cloud)                │
│   ──────────────              ────────────────               │
│                                                              │
│   • Wake word                 • ASR                         │
│   • VAD                       • Intent classification        │
│   • Mic capture               • Entity extraction          │
│   • Sensor access             • Memory lookup              │
│   • Local embedding           • Knowledge search            │
│   • Matter control            • Response generation        │
│   • Local playback            • Calendar sync               │
│   • Notifications             • Cross-device context        │
│   • Screen display            • User profile               │
│   • Privacy processing        • Personalization             │
│                              • Recommendations             │
│                              • Analytics                   │
│                                                              │
│   HYBRID:                HYBRID:                          │
│   • Location → place    ←   • Cross-device presence       │
│   • Smart home control←     • Scene orchestration          │
│   • Voice embed      →     • Match & profile              │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Priority

### Phase 1: Core Voice (Client → Server)

| Step | Implement | Where |
|------|-----------|-------|
| Wake word | 1 | Client |
| VAD | 1 | Client |
| Audio send | 1 | Client → Server |
| ASR | 1 | Server |
| Basic response | 1 | Server |

### Phase 2: Identity (Hybrid)

| Step | Implement | Where |
|------|-----------|-------|
| Embedding extract | 2 | Client |
| Match | 2 | Server |
| Profile load | 2 | Server |

### Phase 3: Context (Hybrid)

| Step | Implement | Where |
|------|-----------|-------|
| Sensor collection | 3 | Client |
| Place inference | 3 | Client |
| Cross-device | 3 | Server |

### Phase 4: Actions (Hybrid)

| Step | Implement | Where |
|------|-----------|-------|
| Smart home | 4 | Client (Matter) |
| Notifications | 4 | Client + Server |
| Playback | 4 | Client |

---

**End of Specification**