# Butler - The Perfect Specification

**Core Principle:** Every feature exists to serve Identity → Context → Intent → Action.

---

## The Four Foundations Answered

| Foundation | Question | Butler's Answer |
|------------|----------|----------------|
| **Identity** | WHO is this? | Voice → Speaker → Profile |
| **Context** | WHERE + WHEN + WHAT around? | Location, device, time, environment |
| **Intent** | WHAT do they WANT? | Command, question, request, conversation |
| **Action** | HOW do I RESPOND? | Spoken, visual, notification, action |

---

## The Complete Butler Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ SPEECH   │───▶│IDENTITY  │───▶│CONTEXT   │───▶│ INTENT  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                         │               │              │
                         └───────────────┼──────────────┘
                                         ▼
                                   ┌──────────┐
                                   │ ACTION   │
                                   └──────────┘
```

---

## Identity - WHO?

### Voice Recognition Flow

```
Audio Input
    │
    ▼
┌────────────┐     ┌────────────┐
│Wake Word   │────▶│VAD        │ ──▶ Speech Segment
│Detector    │     │Detector   │
└────────────┘     └─────┬──────┘
                          │
                          ▼
                  ┌────────────┐
                  │Speaker     │
                  │Embedding   │
                  └─────┬──────┘
                        │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │Enrolled  │  │Enrolled  │  │Unknown  │
    │Match     │  │No Match  │  │First Use │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │            │            │
         ▼            ▼            ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │User      │  │ Guest   │  │Guest    │
    │Profile   │  │Mode    │  │Track    │
    └──────────┘  └──────────┘  └──────────┘
```

### User Profile (Stored)

```json
{
  "user_id": "usr_001",
  "voice_enrolled": true,
  "voice_embedding": "vec_abc",
  "name": "Abhishek",
  "preferences": {
    "language": "en",
    "voice_speed": 1.0,
    "volume": 0.7,
    "unit_system": "imperial"
  },
  "trusted_devices": ["phone_01", "speaker_living"],
  "routines": {
    "morning": ["lights_on", "weather_report"],
    "evening": ["dim_lights", "quiet_mode"]
  }
}
```

---

## Context - WHERE + WHEN + WHAT AROUND?

### Context Collection

```json
{
  "timestamp": "2026-04-20T08:12:00Z",
  
  "location": {
    "type": "home",           // home | office | car | traveling
    "confidence": 0.95,
    "method": "wifi_ssid"      // gps | wifi | ble | calendar
  },
  
  "time": {
    "hour": 8,
    "day": "monday",
    "routine": "morning"
  },
  
  "nearest_device": {
    "id": "phone_01",
    "distance_m": 0.5,
    "type": "mobile",
    "best_for": "private_response"
  },
  
  "devices_nearby": [
    {"id": "speaker_living", "audio": "playing"},
    {"id": "tv_living", "video": "on"}
  ],
  
  "in_meeting": false,
  "calendar_next": "standup_0900"
}
```

### Context → Response Channel

| Location | Day/Time | Meeting | Response |
|-----------|----------|---------|----------|
| home | morning | no | Speaker (spoken) |
| home | any | no | Any (user choice) |
| office | work hours | no | Speaker/Phone |
| office | work hours | yes | Notification only |
| car | driving | yes | Car audio, brief |
| phone | in pocket | no | Haptic + speaker |

---

## Intent - WHAT WANT?

### Intent Classification

| Type | Telltale | Example | Needs |
|------|---------|---------|--------|
| **Command** | Action verb | "Turn off lights" | Execution |
| **Question** | Question word | "What's weather?" | Answer |
| **Request** | Want phrase | "Remind me at 7" | Task creation |
| **Conversation** | No verb | "How was my day?" | Response |
| **Greeting** | Hello/hi | "Hey Butler" | Acknowledge |

### Intent Data Structure

```json
{
  "input_text": "remind me to call mom when i get home",
  
  "intent_type": "request",           // command | question | request | conversation
  "domain": "reminder",                // reminder | smart_home | calendar | etc
  "action": "create_reminder",
  
  "entities": {
    "recipient": "mom",               // extracted from "call mom"
    "trigger": "arrive_home"          // inferred from "when i get home"
  },
  
  "slots_filled": ["recipient", "trigger", "time"],
  "slots_missing": [],
  
  "confidence": 0.91
}
```

---

## Action - HOW RESPOND?

### Response Mode Matrix

| Context | Response Mode | How Selected |
|---------|---------------|---------------|
| Hands free | Spoken | Primary mode |
| Screen visible | Visual | If response needs detail |
| Private place | Visual + haptic | Don't speak |
| Meeting | Notification only | Silent |
| Driving | Spoken, brief | Eyes on road |
| Headphones | Spoken | Private channel |

### Execution Result

```json
{
  "response_mode": "spoken",
  "response_text": "Done. I'll remind you when you get home.",
  "confirm": true,
  
  "action_performed": {
    "tool": "create_reminder",
    "result": "created",
    "reminder_id": "rem_123",
    "scheduled_for": "arrive_home"
  }
}
```

---

## The Five Essential Services

For Identity → Context → Intent → Action to work, Butler needs exactly 5 services:

### 1. Voice Service (Input)

```
INPUT: Audio
  │
  ▼
Wake Word → VAD → ASR → Text
  │
  ▼
OUTPUT: Text + Voice embedding
```

### 2. Identity Service (WHO)

```
INPUT: Voice embedding
  │
  ▼
Match against enrolled embeddings
  │
  ▼
OUTPUT: User ID + Profile + Preferences
```

### 3. Context Service (WHERE/WHEN)

```
INPUT: Sensors + Network + Calendar + Time
  │
  ▼
Aggregate: location + device + time + environment
  │
  ▼
OUTPUT: Context object
```

### 4. Intent Service (WHAT WANT)

```
INPUT: Text + User ID + Context
  │
  ▼
Classify intent → Extract entities → Fill missing slots
  │
  ▼
OUTPUT: Complete intent
```

### 5. Response Service (HOW)

```
INPUT: Intent + Context + User preferences
  │
  ▼
Select mode → Execute tool → Generate response
  │
  ▼
OUTPUT: Spoken/Visual/Action
```

---

## Service Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    BUTLER DATA FLOW                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   SPEECH ────────────────────────────────────────────▶  VOICE SERVICE │
│                                                            │
│                                                         │
│   VOICE SERVICE ─────────────────────────────────────────▶  IDENTITY SERVICE │
│                     voice_embedding                      │
│                                                            │
│                                                         │
│   IDENTITY ──────────────▶  CONTEXT SERVICE              │
│   user_id + preferences      sensor data                │
│                                                            │
│                                                         │
│   CONTEXT ────────────────▶  INTENT SERVICE              │
│   context object            text                        │
│                                                            │
│                                                         │
│   INTENT ────────────────▶  RESPONSE SERVICE             │
│   complete_intent           user_preferences             │
│                                                            │
│                                                         │
│   RESPONSE ───────────────▶  OUTPUT                      │
│   spoken/visual/action     user                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## No Random Features - The Rule

Every feature must pass this test:

```
NEW FEATURE PROPOSED
    │
    ▼
Does it help identify WHO?
    │   YES → Include in Identity Service
    │   NO
    ▼
Does it help know WHERE/WHEN?
    │   YES → Include in Context Service  
    │   NO
    ▼
Does it help understand WHAT WANT?
    │   YES → Include in Intent Service
    │   NO
    ▼
Does it help respond HOW?
    │   YES → Include in Response Service
    │   NO
    ▼
DO NOT INCLUDE

────────────────────────────────────────────────────────
Examples of REJECTED features:

• Fun facts at random              → WHAT WANT? No
• Unsolicited news                 → WHAT WANT? No
• Tracking without consent         → WHO? No consent
• Cross-device without permission → WHERE? No permission
• Random recommendations              → WHAT WANT? Not asked
```

---

## Perfect User Journeys

### Journey 1: Morning at Home

```
User: "Hey Butler, good morning"

1. VOICE detects "Hey Butler"
2. VAD detects speech start
3. ASR converts to text
4. IDENTITY matches voice → Abhishek
5. CONTEXT → home, morning, 7am, kitchen nearby
6. INTENT → greeting + morning routine request
7. RESPONSE → "Good morning, Abhishek! 
   It's Monday. Standup at 9, weather is 72° sunny.
   Start your morning routine?"

→ Action executed: lights_on, weather check
→ Response mode: spoken on speaker
```

### Journey 2: Leaving Office

```
User: "Remind me to call Sarah when I leave"

1. VOICE detects "Butler"
2. IDENTITY → Abhishek (still authenticated)
3. CONTEXT → office, leaving now, 10min drive
4. INTENT → create_reminder with trigger arrive_home
5. RESPONSE → "Done" (brief, spoken)

→ Later at home:
→ Trigger fires → "Time to call Sarah"
```

### Journey 3: Driving

```
User: "What's my next meeting?"

1. VOICE + IDENTITY
2. CONTEXT → in car, driving
3. INTENT → get_calendar, next event
4. RESPONSE → "Standup at 9am" (brief, spoken)
```

---

## What Butler NEVER Does

| Never Does | Because |
|-------------|---------|
| Speaks unsolicited | Violates WHAT WANT |
| Tracks without consent | Violates WHO |
| Recommends unasked | Violates WHAT WANT |
| Tracks location always | Violates WHERE |
| Shows notifications in meeting | Violates WHEN |

---

**Specification Complete**

Every feature: serves WHO / WHERE+WEN / WHAT WANT / HOW RESPOND

Nothing random. Everything essential.

---

**End of Specification**