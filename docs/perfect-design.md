# Butler - The Perfect Design

**Version:** 1.0  
**Core Principle:** No random features. Every capability serves identity, context, intent, or action.

---

## The Four Foundations

Every Butler capability exists to serve one of these four purposes:

| Foundation | Question It Answers | Core Capability |
|------------|-------------------|----------------|
| **Identity** | WHO is this? | Speaker recognition, user profiles, preferences |
| **Context** | WHERE + WHEN + WHAT around? | Location, device proximity, time, environment |
| **Intent** | WHAT do they WANT? | Understanding commands, questions, needs |
| **Action** | HOW do I RESPOND? | Execution, response selection, feedback |

```
┌─────────────────────────────────────────────────────────┐
│                    BUTLER FUNDAMENTALS              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   IDENTITY ────▶ What I know about you                 │
│      │                                                  │
│      ▼                                                  │
│   CONTEXT ───▶ What I know about around you            │
│      │                                                  │
│      ▼                                                  │
│    INTENT ───▶ What you want from me                   │
│      │                                                  │
│      ▼                                                  │
│    ACTION ───▶ How I respond                           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## The Identity Layer

### What Butler Needs to Know About You

| Information | Source | Why |
|-------------|--------|-----|
| Your name | Enrollment | Personalization |
| Your voice | Voiceprint | Auth + personalization |
| Your face | (optional) Face enrollment | Quick identity |
| Your preferences | Usage learning | Better responses |
| Your devices | Pairing | Where to respond |
| Your routines | Pattern learning | Anticipation |
| Your health goals | (opt-in) Health data | Health-aware |

### How Identity Works

```
┌─────────────────────────────────────────────────────────┐
│                    IDENTITY FLOW                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   Voice enters                                          │
│      │                                                  │
│      ▼                                                  │
│   ┌───────────────┐     ┌───────────────┐              │
│   │ Wake Word    │────▶│ VAD          │              │
│   │ Detector    │     │ Detector     │              │
│   └───────────────┘     └─────┬─────────┘              │
│                               │                          ��
│                               ▼                          │
│                        ┌───────────────┐              │
│                        │ Speaker     │              │
│                        │ Embedding   │              │
│                        └─────┬───────┘              │
│                              │                          │
│                              ▼                          │
│   ┌───────────────┐     ┌───────────────┐              │
│   │ Enrolled?    │────▶│ Unknown?     │              │
│   │ (matched)    │     │ (track only)  │              │
│   └───────┬───────┘     └───────────────┘              │
│           │                                              │
│           ▼                                              │
│   ┌───────────────┐                                      │
│   │ User Profile │                                      │
│   │ + Preferences│ ◀── This IS "Identity"             │
│   └───────────────┘                                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Identity Data Stored

```json
{
  "user_id": "usr_abc123",
  "name": "Abhishek",
  "voiceprint": {
    "model": "ecapa-tdnn",
    "embedding_id": "voice_emb_001",
    "enrolled": "2026-01-15",
    "last_verified": "2026-04-20"
  },
  "faceprint": {
    "model": "arcface", 
    "embedding_id": "face_emb_001",
    "enrolled": "2026-02-01"
  },
  "devices": [
    {"device_id": "phone_01", "type": "android", "trusted": true},
    {"device_id": "speaker_01", "type": "speaker", "room": "living"}
  ],
  "preferences": {
    "voice_speed": 1.0,
    "volume": 0.7,
    "language": "en",
    "notifications_channel": "speakers"
  },
  "routines": [
    {"name": "morning", "time": "07:00", "actions": ["lights_on", "weather"]}
  ],
  "health_goals": {
    "opt_in": true,
    "sleep_target": 8,
    "activity_target": 30
  }
}
```

---

## The Context Layer

### What Butler Knows About Around You

| Context Type | Examples | How Obtained |
|--------------|----------|--------------|
| **Location** | home, office, car | GPS, WiFi, time |
| **Device proximity** | which device nearest | BLE, UWB, WiFi |
| **Time of day** | morning routine | System clock |
| **Environment** | alone, meeting, driving | Calendar, sensors |
| **Nearby people** | family, coworkers | Face, voice |
| **Activity** | walking, driving | Motion sensors |
| **Room** | kitchen, bedroom | Room inference |

### Context Information Flow

```json
{
  "context_id": "ctx_001",
  "timestamp": "2026-04-20T08:12:00Z",
  
  "location": {
    "place": "home",
    "confidence": 0.95,
    "method": "wifi_ssid"
  },
  
  "device_proximity": [
    {"device_id": "phone_01", "distance_m": 0.5, "method": "ble"},
    {"device_id": "speaker_01", "distance_m": 3.0, "method": "wifi"}
  ],
  
  "nearest_device": {
    "device_id": "phone_01",
    "type": "mobile",
    "capabilities": ["voice", "screen", "vibration"],
    "best_for": "private_response"
  },
  
  "environmental": {
    "noise_level_db": 45,
    "ambient_light": "bright",
    "occupied_rooms": ["kitchen"],
    "people_present": ["user"]
  },
  
  "time": {
    "hour": 8,
    "day_of_week": "monday",
    "in_routine": "morning"
  },
  
  "calendar": {
    "next_event": "standup",
    "in_meeting": false,
    "free_until": "09:00"
  }
}
```

### How Butler Selects Response Device

```
If user is at home AND closest to speaker:
    → Respond on living room speaker (spoken)

If user is in car:
    → Respond on car audio (spoken, brief)

If user is wearing earbuds:
    → Respond on earbuds (spoken, private)

If user is looking at phone:
    → Show on phone screen (visual)

If user is at office AND in meeting:
    → Log for later, don't interrupt

If user is sleeping:
    → Vibrate only, silent
```

---

## The Intent Layer

### What You Want From Butler

| Intent Type | Examples | Processing |
|------------|----------|-------------|
| **Command** | "Turn off lights" | Action extraction |
| **Question** | "What's the weather?" | Search + answer |
| **Request** | "Remind me at 7" | Task creation |
| **Conversation** | "How was my day?" | Memory + response |
| **Proactive** | ( Butler initiates ) | Recommendation |

### Intent Classification

```json
{
  "intent_id": "intent_001",
  "raw_text": "remind me to call mom after 7",
  
  "classification": {
    "type": "request",
    "domain": "reminder",
    "action": "create_reminder",
    "entities": {
      "recipient": "mom",
      "time_relative": "after 7"
    }
  },
  
  "slots_filled": [
    {"slot": "recipient", "value": "mom", "source": "memory"},
    {"slot": "time", "value": "19:00", "source": "computed"}
  ],
  
  "slots_missing": [],
  
  "confidence": 0.89,
  "requires_clarification": false
}
```

### The Intent Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                  INTENT PIPELINE                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   Speech Audio                                          │
│       │                                                 │
│       ▼                                                 │
│   ┌─────────────┐     ┌─────────────┐                  │
│   │ Wake Word  │────▶│ VAD         │                  │
│   │ Detector   │     │ Detector    │                  │
│   └─────────────┘     └──────┬──────┘                  │
│                              │                          │
│                              ▼                          │
│   ┌─────────────────────────────────────────────────┐   │
│   │              ASR (WhisperX)                    │   │
│   │         Convert speech to text                    │   │
│   └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                          ▼                              │
│   ┌─────────────────────────────────────────────────┐   │
│   │           Intent Classifier (LLM)                │   │
│   │      Classify: command, question, request       │   │
│   └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                          ▼                              │
│   ┌─────────────────────────────────────────────────┐   │
│   │              Entity Extractor                   │   │
│   │   Extract: who, what, when, where, how         │   │
│   └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                          ▼                              │
│   ┌─────────────────────────────────────────────────┐   │
│   │          Slot Filler (from memory/context)      │   │
│   │    Fill missing from: identity, context      │   │
│   └──────────────────────┬──────────────────────────┘   │
│                          │                              │
│                          ▼                             │
│   ┌────────────────────────��────────────────────────┐   │
│   │           Complete Intent                      │   │
│   │   { action, entities, confidence }             │   │
│   └─────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## The Action Layer

### How Butler Responds

| Response Mode | When Used | Example |
|---------------|-----------|----------|
| **Spoken** | Voice interface | "Your meeting is at 10" |
| **Visual** | Screen available | Card with details |
| **Written** | Chat/text | "Reminder created ✓" |
| **Notification** | Background | Push notification |
| **Action** | Tool execution | "Turning on lights..." |
| **Deferred** | Busy/offline | Log for later |

### Response Selection Logic

```
Response Mode Selection:

1. Can user hear me?
   YES → Prefer spoken
   NO  → Skip to visual/written

2. Is user moving/walking?
   YES → Prefer spoken (hands-free)
   NO  → Can offer visual

3. Is response urgent?
   YES →spoken + notification
   NO  → Normal priority flow

4. Is user in private place?
   YES → Prefer visual, not spoken
   NO  → Open choice

5. Is user in meeting?
   YES → Notification only, silent
   NO  → Normal flow

6. Does response need details?
   YES → Visual > Written > Spoken
   NO  → Short response ok
```

### Action Execution

```json
{
  "action_id": "action_001",
  "intent_id": "intent_001",
  
  "execution": {
    "tool": "create_reminder",
    "parameters": {
      "recipient": "mom",
      "time": "19:00",
      "note": "call"
    }
  },
  
  "response": {
    "mode": "spoken",
    "text": "I'll remind you to call mom at 7pm",
    "confirm": true
  },
  
  "result": {
    "success": true,
    "reminder_id": "reminder_xyz",
    "scheduled_for": "2026-04-20T19:00:00Z"
  }
}
```

---

## The Complete Butler Loop

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE BUTLER LOOP (PERFECT)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                      │
│      ┌─────────┐                                                     │
│      │ SPEECH  │                                                     │
│      │ INPUT   │                                                     │
│      └───┬─────┘                                                     │
│          │                                                          │
│          ▼                                                          │
│  ┌───────────────┐                                                   │
│  │   IDENTITY   │ ◀── WHO? (voice → speaker embedding → profile)     │
│  │   LAYER     │     Checks: enrolled user? preferences?           │
│  └───────┬───────┘                                                   │
│          │                                                          │
│          ▼                                                          │
│  ┌───────────────┐                                                   │
│  │   CONTEXT    │ ◀── WHERE? (location, device proximity, time)     │
│  │   LAYER     │     Knows: home/office, nearby devices, environment    │
│  └───────┬───────┘                                                   │
│          │                                                          │
│          ▼                                                          │
│  ┌───────────────┐                                                   │
│  │   INTENT    │ ◀── WHAT WANT? (classify → extract → fill)         │
│  │   LAYER     │     Understands: command, question, request         │
│  └───────┬───────┘                                                   │
│          │                                                          │
│          ▼                                                          │
│  ┌───────────────┐                                                   │
│  │   ACTION     │ ◀── HOW RESPOND? (select mode → execute → respond) │
│  │   LAYER     │     Chooses: spoken/visual/notification/action       │
│  └───────┬───────┘                                                   │
│          │                                                          │
│          ▼                                                          │
│      ┌─────────┐                                                    │
│      │ OUTPUT  │                                                    │
│      │ (RESPONSE)                                                   │
│      └─────────┘                                                    │
│                                                                      │
│   ════════════════════════════════════════════════════════════════════│
│   Every component serves IDENTIFY → CONTEXT → INTENT → ACTION          │
│   No feature exists without answering one of these four questions    │
│   ════════════════════════════════════════════════════════════════════│
```

---

## What Butler Does NOT Do

| Rejected Feature | Reason |
|------------------|--------|
| Random weather facts | Not requested |
| Unsolicited news | Not asked |
| Unprompted recommendations | Violates privacy |
| Tracking without consent | Identity violation |
| Cross-device without permission | Trust violation |
| "Fun facts" | Not in intent pipeline |

---

## The Five Essential Services

Based on the four foundations, Butler needs exactly five services:

### 1. Identity Service

- Speaker verification
- User profile management
- Preferences storage
- Device pairing

### 2. Context Service

- Location awareness
- Device proximity
- Time/routine tracking
- Environmental awareness

### 3. Conversation Service

- Wake word detection
- Voice activity detection
- Speech-to-text
- Intent classification
- Entity extraction

### 4. Execution Service

- Tool registry
- Action execution
- Response generation

### 5. Memory Service

- Short-term conversation
- Long-term user memory
- Knowledge graph

---

## Service Connections

```
┌──────���─���────────────────────────────────────────────────────────┐
│                    BUTLER SERVICES                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐                                              │
│   │ CONVERSATION │ ◀── Speech input                              │
│   │  SERVICE    │ ──▶ Intent classification                    │
│   └──────┬───────┘                                              │
│          │                                                      │
│   ┌──────┼──────┐    ┌──────────────┐                           │
│   │      │     │    │  IDENTITY   │                           │
│   ▼      ▼     ▼    │   SERVICE   │ ◀── Speaker profile        │
│   ┌──────────────┐  └──────┬───────┘                           │
│   │  EXECUTION   │         │                                   │
│   │   SERVICE   │         ▼                                   │
│   └──────┬───────┘    ┌──────────────┐                          │
│          │           │  CONTEXT    │                           │
│   ┌──────┴───────┐    │  SERVICE   │ ◀── Location, proximity   │
│   │   MEMORY     │    └──────┬───────┘                          │
│   │   SERVICE   │            │                                   │
│   └─────────────┘            ▼                                   │
│                        (feedback loop)                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Perfect User Journey

### 1. Morning - At Home

```
User: "Hey Butler, good morning"
  │
  ▼ IDENTITY
Butler: "Good morning, Abhishek" (voice matched)
  │
  ▼ CONTEXT
Butler knows: at home, 7am, kitchen nearby, phone in pocket
  │
  ▼ INTENT
Butler understands: greeting + morning routine check
  │
  ▼ ACTION
Butler responds: "Good morning! It's Monday, 7am. 
  Your standup is at 9. Weather is sunny, 72°. 
  Want me to start your morning routine?"
```

### 2. Leaving - At Office

```
User: "Butler, remind me to call Sarah when I get home"
  │
  ▼ IDENTITY
Butler: (already known, no check needed)
  │
  ▼ CONTEXT
Butler knows: at office, leaving now, 10 min drive home
  │
  ▼ INTENT
"create_reminder { recipient: sarah, trigger: arrive_home }"
  │
  ▼ ACTION
"Done. I'll remind you when you get home."
  │
  Later at home:
"Remember: call Sarah"
```

### 3. Evening - Driving

```
User: "Butler, what's on my calendar tomorrow?"
  │
  ▼ IDENTITY
Butler: (already known)
  │
  ▼ CONTEXT
Butler knows: in car, driving, voice only interface
  │
  ▼ INTENT
"get_calendar { date: tomorrow }"
  │
  ▼ ACTION (spoken, brief)
"Tomorrow you have: standup at 9, lunch with John at noon, 
  and a 3pm deadline for the project."
```

---

**This is the perfect design. Every feature serves identity, context, intent, or action. Nothing random. Everything essential.**

---

**End of Perfect Design**