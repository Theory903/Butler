# Butler Realtime Listening + Turn-Taking + Importance Engine Specification

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## Executive Summary

This specification defines Butler's real-time audio interaction system for knowing when to listen, when to speak, and when to stay silent. The system separates wake-word gating from directed-command detection, turn-taking prediction, and importance scoring.

### Core Capabilities

- **Wake-word gate**: "Butler" detection
- **Pre-wakeup command**: Directed speech without wake word
- **Turn-taking prediction**: Know when to respond
- **Barge-in handling**: Interrupt-aware response
- **Importance scoring**: Urgent vs optional
- **Policy gating**: When to actually respond
- **Contextual resolution**: "Is B's fact true?" → resolve referents

### SOTA Stack

| Component | Model | Purpose |
|-----------|-------|---------|
| Wake word | openWakeWord | Keyword detection |
| VAD | Silero VAD | Speech boundaries |
| Diarization | pyannote | Speaker segmentation |
| Speaker ID | ECAPA-TDNN | Identity verification |
| ASR | WhisperX | Timestamped transcription |
| Turn model | Custom | Hold/shift prediction |
| Importance | Custom classifier | Urgency scoring |
| Reference resolution | Butler-native | Context tracking |

---

## 1. System Architecture

### 1.1 Full Realtime Loop

```
┌─────────────────────────────────────────────────────────────────┐
│           BUTLER REALTIME LISTENING LOOP                    │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  [Microphone Array / Room Audio]                            │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │         STAGE 1: Wake Word                  │        │
│  │    openWakeWord detection                   │        │
│  │    - "Hey Butler", custom phrases           │        │
│  │    → activation event                    │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │         STAGE 2: VAD                        │        │
│  │    Silero VAD                              │        │
│  │    - speech start/stop                     │        │
│  │    → utterance segments                 │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌──────────────────────────────────────────��──┐        │
│  │         STAGE 3: Diarization                │        │
│  │    pyannote                              │        │
│  │    - who spoke when                      │        │
│  │    → speaker segments                │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │         STAGE 4: Speaker Verification      │        │
│  │    ECAPA-TDNN embeddings                 │        │
│  │    → trusted user? → policy lane         │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │         STAGE 5: ASR + Alignment           │        │
│  │    WhisperX                             │        │
│  │    → transcribed text + timestamps    │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │    STAGE 6: Turn-Taking Predictor         │        │
│  │    - acoustic cues                      │        │
│  │    - linguistic cues                 │        │
│  │    - interaction cues               │        │
│  │    → shift / hold decision           │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │    STAGE 7: Importance Scorer            │        │
│  │    - urgency detection               │        │
│  │    - personal relevance           │        │
│  │    - criticality               │        │
│  │    → priority score           │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────────────────────────────────────────┐        │
│  │    STAGE 8: Policy Gate                  │        │
│  │    → response mode selection           │        │
│  └─────────────────────────────────────────────┘        │
│        │                                                 │
│        ▼                                                 │
│  ┌─────────��───────────────────────────────────┐        │
│  │    STAGE 9: Barge-in Handler           │        │
│  │    - stop TTS                      │        │
│  │    - backchannel vs interrupt      │        │
│  │    - resume decision           │        │
│  └─────────────────────────────────────────────┘        │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Staged Trigger Model

```
┌─────────────────────────────────────────────────────────────────┐
│           STAGED TRIGGER MODEL                            │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  STAGE 1: Passive Listen (always-on)                     │
│  ─────────────────────────────────────                 │
│  • Wake word detector running                         │
│  • VAD only                                       │
│  • Minimal compute (~100mW)                        │
│  • No transcription until triggered               │
│                                                          │
│  STAGE 2: Directed Attention                        │
│  ─────────────────────────────────────                 │
│  • Wake word hit: "Butler," "Hey Butler"           │
│  • OR: command form from verified speaker          │
│  • OR: second-person phrasing                  │
│  → Enter active conversation mode                 │
│                                                          │
│  STAGE 3: Conversation Follow Mode                 │
│  ─────────────────────────────────────                 │
│  • Short-lived active context (30-60s)            │
│  • Turn-taking enabled                         │
│  • Barge-in enabled                          │
│  • Remembers active speaker + context           │
│                                                          │
│  STAGE 4: Importance Override                    │
│  ─────────────────────────────────────                 │
│  • Urgency phrases: "help", "emergency"        │
│  • Repeated name calling                       │
│  • Alarm / safety events                    │
│  • High-priority household rules            │
│  → React even without wake word               │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Specifications

### 2.1 Wake Word Detection

```
┌─────────────────────────────────────────────────────────────────┐
│               WAKE WORD DETECTION                          │
├───��─��───────────────────────────────────────────────────────────┤
│ Model: openWakeWord                                         │
│                                                          │
│ Default Phrases:                                          │
│ • "Hey Butler"                                          │
│ • "Butler"                                            │
│ • "Hey Jarvis" (optional)                               │
│                                                          │
│ Configuration:                                           │
│ • Detection threshold: 0.5                              │
│ • False activation filter: 3 consecutive           │
│ • Cooldown: 2 seconds                                  │
│ • Custom wake word support                                │
│                                                          │
│ Performance:                                           │
│ • Latency: <50ms detection                              │
│ • Power: <100mW always-on                             │
│ • Accuracy: >95% on clear audio                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Voice Activity Detection

```
┌─────────────────────────────────────────────────────────────────┐
│               VOICE ACTIVITY DETECTION                     │
├─────────────────────────────────────────────────────────────────┤
│ Model: Silero VAD                                            │
│                                                          │
│ Configuration:                                           │
│ • Speech threshold: 0.5                                  │
│ • Min speech duration: 250ms                             │
│ • Max speech segment: 30 seconds                         │
│ • Sample rate: 16kHz                                     │
│                                                          │
│ Output:                                                  │
│ • speech_start timestamp                                   │
│ • speech_end timestamp                                    │
│ • speech_probability per chunk                          │
│ • audio_energy levels                                  │
│                                                          │
│ Real-time:                                              │
│ • Chunk processing: 100ms                               │
│ • Sub-millisecond on CPU                                │
│ • Streaming mode enabled                               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Diarization

```
┌─────────────────────────────────────────────────────────────────┐
│               SPEAKER DIARIZATION                          │
├─────────────────────────────────────────────────────────────────┤
│ Model: pyannote                                             │
│                                                          │
│ Output:                                                  │
│ • Speaker segments: who spoke when                        │
│ • Overlap detection                                      │
│ • Cluster IDs                                         │
│                                                          │
│ Configuration:                                           │
│ • Max speakers: 10                                     │
│ • Min segment: 1 second                               │
│ • Embedding: ECAPA-TDNN                               │
│                                                          │
│ Use:                                                   │
│ • Know who is speaking                                │
│ • Track conversation flow                           │
│ • Identify directed vs background speech       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 Speaker Verification

```
┌─────────────────────────────────────────────────────────────────┐
│               SPEAKER VERIFICATION                      │
├─────────────────────────────────────────────────────────────────┤
│ Model: ECAPA-TDNN                                         │
│                                                          │
│ Enrollment:                                              │
│ • 10-30 seconds per user                              │
│ • 5+ distinct utterances                              │
│                                                          │
│ Thresholds:                                              │
│ ��� Verification: 0.68 cosine similarity           │
│ • Strict for sensitive commands: 0.80              │
│                                                          │
│ Output:                                                  │
│ • speaker_id                                          │
│ • is_trusted: boolean                                   │
│ • confidence: 0.0-1.0                                │
│ • verification_method: "ecapa" / "wake_word"      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 ASR with Alignment

```
┌─────────────────────────────────────────────────────────────────┐
│               ASR + ALIGNMENT                         │
├─────────────────────────────────────────────────────────────────┤
│ Model: WhisperX                                             │
│                                                          │
│ Output:                                                  │
│ • Full transcript                                       │
│ • Word-level timestamps                                  │
│ • Word confidence scores                              │
│ • Speaker assignment per segment                  │
│                                                          │
│ Configuration:                                           │
│ • Model: base (default), large (SOTA)                 │
│ • Language: auto-detect                                 │
│ • Diarization-aware                                   │
│                                                          │
│ Use:                                                   │
│ • Know what was said                                    │
│ • Know when it was said                                │
│ • Know who said it                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Turn-Taking Prediction

### 3.1 Turn State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│               TURN STATE MACHINE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  States:                                                   │
│                                                          │
│  ┌─────────┐     speak_start      ┌─────────────┐          │
│  │ LISTEN  │ ───────────────▶ │ SPEAKING   │          │
│  │         │ ◀────────────── │            │          │
│  └─────────┘     silence_end   └─────────────┘          │
│       │                                              │
│       │ turn_shift                                      │
│       ▼                                              │
│  ┌─────────────┐                                    │
│  │ WAIT FOR │  (after user speaks)                    │
│  │ RESPONSE │                                    │
│  └─────────────┘                                    │
│                                                          │
│  Transitions:                                             │
│  • LISTEN → SPEAKING: user starts speaking           │
│  • SPEAKING → LISTEN: silence > threshold           │
│  • shift decision from turn model                │
│  • WAIT_FOR_RESPONSE → LISTEN: user addressed         │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Turn Prediction Features

| Category | Feature | Weight |
|----------|---------|--------|
| **Acoustic** | Pitch drop | 0.15 |
| | Hesitation pause > 500ms | 0.20 |
| | Final-lengthening | 0.10 |
| | Silence onset | 0.15 |
| **Linguistic** | Command completion | 0.15 |
| | Question completion | 0.20 |
| | Vocative " Butler" | 0.25 |
| | Command verbs | 0.15 |
| **Interaction** | Device context | 0.10 |
| | Active speaker | 0.15 |
| | Prior turn owner | 0.10 |

### 3.3 Turn Decision Output

```python
class TurnDecision:
    should_respond: bool          # true / false
    turn_state: str              # "shift" / "hold"
    confidence: float            # 0.0 - 1.0
    reason: List[str]            # ["wake_word", "completed_question", ...]
    response_mode: str           # "spoken" / "silent" / "clarify" / "none"
    interrupt_current_tts: bool  # for barge-in
```

### 3.4 Turn Prediction Example

```json
{
  "should_respon d": true,
  "turn_state": "shift",
  "confidence": 0.86,
  "reason": [
    "wake_word",
    "completed_question",
    "speaker_verified"
  ],
  "response_mode": "spoken",
  "interrupt_current_tts": false
}
```

---

## 4. Pre-Wakeup Command Verification

### 4.1 Two-Lane Activation Model

```
┌─────────────────────────────────────────────────────────────────┐
│           TWO-LANE ACTIVATION MODEL                         │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  Lane A: Wake-Word Lane                                 │
│  ─────────────────────────────────────                  │
│  openWakeWord → activation                               │
│  + optional speaker verifier                          │
│  → Full response                                     │
│                                                          │
│  Lane B: Verified Direct-Command Lane                   │
│  ─────────────────────────────────────                  │
│  VAD → diarization → speaker verification            │
│  → directed-command classifier                     │
│  → turn detector → policy gate                    │
│  → activation (if passes)                          │
│                                                          │
│  Runtime Logic:                                         │
│  ─────────────────────────────────────                  │
│  audio                                               │
│   │                                                  │
│   ▼                                                  │
│  VAD                                                 │
│   │                                                  │
│   ├── wake_word detected ───▶ activate                    │
│   │                                                  │
│   └── no wake_word                                   │
│        │                                             │
│        ├── speaker_verified = true                    │
│        │   AND directed_command = true           │
│        │   AND confidence > 0.7              │
│        │   AND policy allows                     │
│        │        ▼                           │
│        │    activate                         │
│        │                                             │
│        └── otherwise → ignore                  │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Directed Command Detection

```python
class DirectedCommandClassifier:
    """Detects commands directed at Butler without wake word"""
    
    # Command form patterns
    imperative_verbs = [
        "send", "remind", "call", "open", "turn", 
        "set", "get", "show", "play", "stop"
    ]
    
    # Second-person patterns
    second_person = [
        "can you", "could you", "please",
        "tell me", "what's", "how do"
    ]
    
    # Context carryover patterns
    carryover = [
        "and then", "what about", "also",
        "same time", "tomorrow", "later"
    ]
    
    def classify(utterance: str, context: Dict) -> Dict:
        # Check command form
        has_imperative = any(v in utterance.lower() for v in self.imperative_verbs)
        
        # Check second-person
        has_second_person = any(p in utterance.lower() for p in self.second_person)
        
        # Check carryover from active context
        has_context = context.get("active_referent") is not None
        
        # Compute directed score
        score = 0.0
        if has_imperative: score += 0.4
        if has_second_person: score += 0.3
        if has_context: score += 0.3
        
        return {
            "is_directed": score > 0.6,
            "confidence": score,
            "reason": [...] 
        }
```

### 4.3 Activation Policies

```
┌─────────────────────────────────────────────────────────────────┐
│           ACTIVATION POLICIES                            │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  STRICT:                                                  │
│  ─────────────────────────────────────                    │
│  • Wake word required for everything                      │
│  • Only emergency phrases bypass                    │
│  • No direct commands without wake                  │
│                                                          │
│  BALANCED (Default):                                     │
│  ─────────────────────────────────────                    │
│  • Wake word preferred                             │
│  • Trusted direct commands in active context     │
│  • Trusted commands on trusted devices         │
│                                                          │
│  AMBIENT PREMIUM:                                        │
│  ─────────────────────────────────────                    │
│  • Verified direct commands allowed              │
│  • Urgent phrases can interrupt                │
│  • Unknown speakers: low-risk commands only   │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Activation Output Example

```json
{
  "activation_mode": "verified_direct_command",
  "speaker_id": "usr_abhi",
  "speaker_verified": true,
  "command_directed_to_butler": true,
  "confidence": 0.89,
  "utterance": "remind me to call mom at 7",
  "allowed": true,
  "policy_reason": [
    "trusted_speaker",
    "command_form",
    "active_home_mode"
  ]
}
```

### 4.5 What Should NOT Trigger

| Pattern | Example | Should |
|---------|---------|--------|
| TV audio | "Hey Google, play music" | ❌ Ignore |
| Two people talking | "I think we should..." | ❌ Ignore |
| Quoted speech | "Butler said to..." | ❌ Ignore |
| Unknown speaker | "turn off lights" | ❌ Require wake |
| Background imperative | (TV: "call mom") | ❌ Ignore |

### 4.6 Speaker Verification Integration

```
Enrollment Requirements:
• 10-30 seconds clean speech per trusted user
• 5+ distinct utterances
• Re-enroll after 90 days

Threshold Configuration:
• Standard commands: 0.68
• Financial commands: 0.80 (stricter)
• Health commands: 0.80 (stricter)
• Lock/camera: 0.85 (strictest)
• Unverified: fall back to wake-word

Logging:
• Log activation reason every time
• Log confidence scores
• Audit trail for security
```

---

## 5. Importance Scoring

### 5.1 Priority Classification

```python
class ImportanceScorer:
    """Score urgency and importance of utterances"""
    
    urgency_keywords = [
        "now", "immediately", "emergency",
        "help", "fire", "fall", "call 911",
        "urgent", "asap"
    ]
    
    importance_keywords = [
        "reminder", "deadline", "meeting",
        "important", "critical", "must"
    ]
    
    personal_relevance = [
        "butler", "hey", "please",
        "can you", "i need"
    ]
    
    def score(self, utterance: str, speaker_id: str, context: Dict) -> Dict:
        # Urgency detection
        has_urgency = any(k in utterance.lower() for k in self.urgency_keywords)
        
        # Importance
        has_importance = any(k in utterance.lower() for k in self.importance_keywords)
        
        # Directed to Butler
        is_directed = any(k in utterance.lower() for k in self.personal_relevance)
        
        # Trusted speaker
        is_trusted = context.get("speaker_trusted", False)
        
        # Compute combined score
        score = 0.0
        if has_urgency: score += 0.5
        if has_importance: score += 0.2
        if is_directed: score += 0.15
        if is_trusted: score += 0.15
        
        return {
            "priority": "high" if score > 0.7 else "medium" if score > 0.4 else "low",
            "is_urgent": has_urgency,
            "score": score,
            "should_interrupt": score > 0.6,
            "response_urgency": "immediate" if has_urgency else "normal"
        }
```

### 5.2 Response Mode Selection

| Priority | Score | Response Mode |
|----------|-------|------------|
| Urgent | >0.7 | Speak immediately |
| High | 0.5-0.7 | Speak soon |
| Medium | 0.3-0.5 | Normal queue |
| Low | <0.3 | Wait for turn |

### 5.3 Complete Decision Output

```json
{
  "turn_decision": {
    "should_respond": true,
    "turn_state": "shift",
    "confidence": 0.86
  },
  "importance": {
    "priority": "high",
    "is_urgent": true,
    "should_interrupt": true
  },
  "response_mode": "spoken_immediate",
  "interrupt_current_tts": true,
  "policy_gate": {
    "allowed": true,
    "policy": "ambient_premium",
    "reason": "urgent_keyword + trusted_speaker"
  }
}
```

---

## 6. Barge-In Handling

### 6.1 Barge-In Detection

```
┌─────────────────────────────────────────────────────────────────┐
│               BARGE-IN HANDLING                            │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│  Triggers:                                                │
│  • User starts speaking while TTS is playing                │
│  • VAD detects speech during TTS output              │
│  • Overlap detected between TTS and user speech      │
│                                                          │
│  Classification:                                         │
│  • Backchannel: "mm-hmm", "yeah", "ok"                 │
│    → Do not interrupt, acknowledge briefly          │
│                                                          │
│  • True interruption: command word, question           │
│    → Stop TTS immediately                            │
│    → Process new command                             │
│    → Optionally resume                          │
│                                                          │
│  Actions:                                                │
│  1. Stop TTS audio stream                            │
│  2. Flush audio buffer                             │
│  3. Switch to listening mode                      │
│  4. Process interruption                      │
│  5. Decide resume / restart                    │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Barge-In Decision

```python
class BargeInHandler:
    """Handle user interruptions during TTS"""
    
    backchannel_words = [
        "yeah", "yes", "ok", "okay", 
        "mm-hmm", "uh-huh", "sure"
    ]
    
    def classify_interruption(
        self, 
        user_speech: str, 
        overlap_duration_ms: int
    ) -> Dict:
        
        is_backchannel = any(
            w in user_speech.lower() 
            for w in self.backchannel_words
        )
        
        if is_backchannel and overlap_duration_ms < 500:
            return {
                "type": "backchannel",
                "action": "acknowledge",
                "stop_tts": False
            }
        
        return {
            "type": "interruption",
            "action": "stop_and_listen",
            "stop_tts": True,
            "resume_after": True
        }
```

### 6.3 Resume Decision

```
Resume Options:
• No resume: Command was complete
• Restart: Command was interrupted before start
• Resume at point: User said "continue" or "go on"
• New command: Different command issued

Decision factors:
• Command completeness before interrupt
• User intent (resume keyword)
• Time since interruption
• Context continuity
```

---

## 7. Contextual Reference Resolution

### 7.1 The Problem

```
User: "Abhi said B works at Tesla."
Butler: noted.

User: "is B's fact true?"
→ Who is B?
→ What is "the fact"?
→ Answer or clarify?
```

This requires:
1. Active entity tracking
2. Claim tracking
3. Reference resolution
4. Clarification when uncertain

### 7.2 Dialogue State Tracking

```python
class DialogueState:
    """Track conversation state for reference resolution"""
    
    def __init__(self):
        # Active referents: who "B", "he", "that" point to
        self.active_entities: List[EntityRef] = []
        
        # Active claims under discussion
        self.active_claims: List[Claim] = []
        
        # Current topic
        self.current_topic: Optional[str] = None
        
        # Active speaker
        self.active_speaker: Optional[str] = None
        
        # Conversation turn count
        self.turn_count: int = 0
```

### 7.3 Entity Reference Stack

```python
class EntityRef:
    alias: str                # "B", "he", "that company"
    entity_id: str          # "person_002"
    name: str            # "Bharat"
    entity_type: str       # "person", "vehicle", "location"
    confidence: float     # 0.91
    turn_created: int     # turn_41
    last_referenced: int # turn_45
    mentions: int       # count
```

### 7.4 Claim Tracking

```python
class Claim:
    claim_id: str          # "claim_188"
    entity_id: str        # "person_002"
    claim_text: str       # "works at Tesla"
    claim_type: str      # "employment"
    source: str         # "conversation", "memory", "search"
    turn_id: str        # "turn_41"
    verified: bool      # checked externally?
    confidence: float   # 0.85
```

### 7.5 Resolution State Example

```json
{
  "active_entities": [
    {
      "alias": "B",
      "entity_id": "person_002",
      "name": "Bharat",
      "type": "person",
      "confidence": 0.91,
      "turn_created": "turn_41",
      "last_referenced": "turn_45"
    }
  ],
  "active_claims": [
    {
      "claim_id": "claim_188",
      "entity_id": "person_002",
      "claim": "works at Tesla",
      "type": "employment",
      "source": "conversation",
      "turn_id": "turn_41",
      "verified": false,
      "confidence": 0.85
    }
  ],
  "current_topic": "employment",
  "active_speaker": "usr_abhi",
  "turn_count": 45
}
```

### 7.6 Resolution Logic

```python
class ReferenceResolver:
    """Resolve references like 'B', 'that fact', 'he'"""
    
    def resolve(
        self,
        reference_text: str,
        dialogue_state: DialogueState
    ) -> ResolutionResult:
        
        # Parse reference
        # "B" → alias lookup
        # "that fact" → claim lookup
        # "he" → pronoun resolution
        # "that company" → entity type filter
        
        # Search entity stack
        entity_match = self._find_entity(
            reference_text, 
            dialogue_state.active_entities
        )
        
        # Search claim stack
        claim_match = self._find_claim(
            reference_text,
            dialogue_state.active_claims
        )
        
        # Compute confidence
        confidence = max(
            entity_match.confidence if entity_match else 0,
            claim_match.confidence if claim_match else 0
        )
        
        # Decision
        if confidence > 0.82:
            return ResolutionResult(
                resolved=True,
                resolved_text=entity_match.name or claim_match.claim,
                confidence=confidence,
                action="answer_directly"
            )
        elif confidence > 0.65:
            return ResolutionResult(
                resolved=True,
                resolved_text=entity_match.name or claim_match.claim,
                confidence=confidence,
                action="answer_with_assumption"
            )
        else:
            return ResolutionResult(
                resolved=False,
                confidence=confidence,
                action="clarify"
            )
```

### 7.7 Resolution Policies

```json
{
  "reference_resolution": {
    "window_turns": 8,
    "entity_stack_limit": 5,
    "claim_stack_limit": 5,
    "direct_answer_threshold": 0.82,
    "assumed_answer_threshold": 0.65,
    "clarify_below": 0.65
  }
}
```

### 7.8 Clarification Examples

**Low confidence (clarify):**
```
User: "is B's fact true?"
Butler: "Who is B? Could you clarify?"
```

**Medium confidence (assume + mention):**
```
User: "is B's fact true?"
Butler: "You mean Bharat's Tesla job, right? 
I can check that for you."
```

**High confidence (direct):**
```
User: "is B's fact true?"
Butler: "You're asking about Bharat working at Tesla.
Here's what I found..."
```

---

## 8. Audio Modes

### 8.1 Mode A: Passive Ambient

```
Configuration:
• Wake word required for everything
• Only urgent events bypass wake word
• Minimal compute
• Safest privacy

Triggers:
• "Hey Butler" → activate
• "help" (urgent) → react without wake
• "emergency" → react without wake
• policy: strict
```

### 8.2 Mode B: Active Conversation

```
Configuration:
• Short-term follow mode after wake
• Turn-taking enabled
• Barge-in enabled
• Remembers context

Triggers:
• Wake word → active mode (30-60s)
• Verified direct command → active mode
• Turn → hold until silence
• policy: balanced
```

### 8.3 Mode C: High-Awareness Assistant

```
Configuration:
• Room-aware diarization
• Speaker identity memory
• Importance scoring
• Selective intervention

Features:
• Verified direct commands
• Urgent phrase override
• Ambient event monitoring
• Unknown speakers: low-risk only
• policy: ambient_premium
```

### 8.4 Mode Comparison

| Feature | Mode A | Mode B | Mode C |
|---------|-------|-------|-------|
| Wake word | Required | Preferred | Optional |
| Turn-taking | ✗ | ✓ | ✓ |
| Barge-in | ✗ | ✓ | ✓ |
| Importance | ✗ | Basic | Full |
| Direct commands | ✗ | ✓ | ✓ |
| Ambient events | ✗ | ✗ | ✓ |
| Privacy | Highest | High | Medium |

---

## 9. Database Schema

### 9.1 Conversation State Table

```sql
CREATE TABLE conversation_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    
    -- State
    state_type VARCHAR(50),           # "active", "idle"
    mode VARCHAR(50),               # "passive", "active", "ambient"
    
    -- Turn tracking
    turn_count INTEGER DEFAULT 0,
    last_turn_timestamp TIMESTAMP WITH TIME ZONE,
    
    -- Active speaker
    active_speaker_id UUID REFERENCES audio_speakers(id),
    
    -- Context
    current_topic VARCHAR(100),
    active_intent VARCHAR(100),
    
    -- Timing
    mode_started_at TIMESTAMP WITH TIME ZONE,
    last_update_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_conversation_session ON conversation_states(session_id);
```

### 9.2 Entity References Table

```sql
CREATE TABLE entity_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    
    -- Entity
    alias VARCHAR(50) NOT NULL,          # "B", "he"
    entity_id VARCHAR(100),
    entity_type VARCHAR(50),
    display_name VARCHAR(255),
    
    -- Tracking
    confidence_score FLOAT,
    turn_created INTEGER,
    last_referenced INTEGER,
    mention_count INTEGER DEFAULT 1,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE (session_id, alias, entity_id)
);

CREATE INDEX idx_entity_session ON entity_references(session_id);
```

### 9.3 Claims Table

```sql
CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_text TEXT NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    claim_type VARCHAR(50),
    
    -- Source
    source VARCHAR(50),              # "conversation", "memory", "search"
    turn_id VARCHAR(50),
    
    -- Verification
    verified BOOLEAN DEFAULT FALSE,
    verification_date TIMESTAMP WITH TIME ZONE,
    
    -- Confidence
    confidence_score FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_claims_entity ON claims(entity_id);
```

### 9.4 Turn Decisions Table

```sql
CREATE TABLE turn_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Decision
    should_respond BOOLEAN,
    turn_state VARCHAR(50),
    confidence_score FLOAT,
    
    -- Reason
    reason JSONB,
    
    -- Response
    response_mode VARCHAR(50),
    
    -- Importance
    priority VARCHAR(20),
    is_urgent BOOLEAN,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_turn_session ON turn_decisions(session_id);
CREATE INDEX idx_turn_timestamp ON turn_decisions(timestamp DESC);
```

---

## 10. API Reference

### 10.1 Realtime Session API

```python
# Start a realtime session
POST /api/v1/audio/session/start
{
    "device_id": "smart_speaker_02",
    "mode": "active",
    "speaker_id": "usr_abhi"
}

# Process audio chunk
POST /api/v1/audio/session/{session_id}/process
{
    "audio": "base64_encoded_pcm",
    "timestamp_ms": 1234
}

# Get current turn decision
GET /api/v1/audio/session/{session_id}/turn

# Get dialogue state
GET /api/v1/audio/session/{session_id}/state

# Stop session
POST /api/v1/audio/session/{session_id}/stop
```

### 10.2 Reference Resolution API

```python
# Resolve reference in context
POST /api/v1/audio/resolve
{
    "session_id": "sess_123",
    "reference": "B's fact",
    "current_utterance": "is B's fact true?"
}

# Get active entities
GET /api/v1/audio/session/{session_id}/entities

# Get active claims
GET /api/v1/audio/session/{session_id}/claims

# Update reference
PUT /api/v1/audio/session/{session_id}/entities
{
    "alias": "B",
    "entity_id": "person_002"
}
```

### 10.3 Configuration API

```python
# Set activation policy
PUT /api/v1/audio/config/policy
{
    "policy": "balanced",
    "allow_direct_commands": true,
    "require_wake_for_sensitive": true
}

# Set turn-taking thresholds
PUT /api/v1/audio/config/turn-taking
{
    "silence_threshold_ms": 800,
    "confidence_threshold": 0.70,
    "use_acoustic_cues": true,
    "use_linguistic_cues": true
}

# Set reference resolution config
PUT /api/v1/audio/config/reference
{
    "window_turns": 8,
    "entity_stack_limit": 5,
    "direct_answer_threshold": 0.82
}
```

---

## 11. Event Schema

### 11.1 Turn Decision Event

```json
{
  "event_type": "turn_decision",
  "session_id": "sess_123",
  "timestamp": "2026-04-20T08:12:00Z",
  
  "decision": {
    "should_respond": true,
    "turn_state": "shift",
    "confidence": 0.86,
    "reason": [
      "wake_word",
      "completed_question"
    ]
  },
  
  "importance": {
    "priority": "medium",
    "is_urgent": false
  },
  
  "response": {
    "mode": "spoken",
    "interrupt_tts": false
  },
  
  "policy": {
    "allowed": true,
    "policy_name": "balanced"
  }
}
```

### 11.2 Activation Event

```json
{
  "event_type": "activation",
  "session_id": "sess_123",
  "timestamp": "2026-04-20T08:12:00Z",
  
  "activation": {
    "mode": "wake_word",
    "trigger": "hey butler",
    "speaker_verified": true,
    "confidence": 0.97
  },
  
  "speaker": {
    "id": "usr_abhi",
    "is_trusted": true
  },
  
  "policy": {
    "applied": "balanced",
    "direct_commands_allowed": true
  }
}
```

### 11.3 Reference Resolution Event

```json
{
  "event_type": "reference_resolved",
  "session_id": "sess_123",
  "timestamp": "2026-04-20T08:12:00Z",
  
  "input": {
    "reference": "B's fact",
    "utterance": "is B's fact true?"
  },
  
  "resolution": {
    "resolved": true,
    "entity": {
      "alias": "B",
      "name": "Bharat"
    },
    "claim": {
      "claim": "works at Tesla",
      "verified": false
    },
    "confidence": 0.85,
    "action": "answer_directly"
  }
}
```

---

## 12. Latency Budgets

### 12.1 Per-Operation Latency

| Operation | Target | Maximum |
|-----------|--------|---------|
| Wake detection | <50ms | <100ms |
| VAD | <5ms | <10ms |
| Diarization | <500ms | <1s |
| Speaker verification | <100ms | <200ms |
| ASR (per second audio) | <300ms | <500ms |
| Turn prediction | <50ms | <100ms |
| Importance scoring | <20ms | <50ms |
| Reference resolution | <30ms | <100ms |
| **End-to-end command** | **<1s** | **<2s** |

---

## 13. Safety & Privacy

### 13.1 Activation Safeguards

```
┌─────────────────────────────────────────────────────────────────┐
│                    SAFETY RULES                              │
├─────────────────────────────────────────────────────────────────┤
│                                                          │
│ ❌ No voice profiling without consent                       │
│ ❌ No activation without policy                       │
│ ❌ No sensitive commands from unverified users        │
│ ❌ No cross-device tracking without opt-in           │
│ ❌ No surveillance mode                              │
│                                                          │
│ Required for activation:                               │
│ • Policy must be defined                          │
│ • Speaker verification OR wake word              │
│ • Confidence threshold met                    │
│ • Command form detected                       │
│                                                          │
│ Logging required:                                 │
│ • Every activation event                      │
│ • Confidence scores                        │
│ • Policy applied                           │
│ • Resolution decisions                      │
│                                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 13.2 Sensitive Command Thresholds

| Command Type | Min Threshold | Require Wake |
|--------------|-------------|-------------|
| General | 0.68 | No |
| Financial | 0.80 | Yes |
| Health | 0.80 | Yes |
| Lock/Camera | 0.85 | Yes |
| Destructive | 0.90 | Yes |

---

## 14. Hard Boundaries

### 14.1 Consent Requirements

| Action | Consent Required |
|--------|---------------|
| Speaker verification | Enrolled + consent |
| Direct commands | Trusted device/user |
| Always-on listening | Opt-in |
| Ambient events | Opt-in |
| Cross-device tracking | Explicit opt-in |

### 14.2 Privacy Rules

```
┌─────────────────────────────────────────────────────────────────┐
│                    HARD BOUNDARIES                      │
├─────────────────────────────────────────────────────────────────┤
│ ❌ Voice profiling without consent                     │
│ ❌ Activation without policy                   │
│ ❌ Sensitive commands from unknown            │
│ ❌ Cross-device tracking without opt-in      │
│ ❌ Surveillance mode                          │
│ ❌ Random wake-word activation               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 15. Model References

| Model | Repository | Purpose |
|-------|-----------|---------|
| openWakeWord | https://github.com/dscripka/openWakeWord | Wake word |
| Silero VAD | https://github.com/snakers4/silero-vad | VAD |
| pyannote | https://github.com/pyannote/pyannote-audio | Diarization |
| ECAPA-TDNN | https://github.com/TaoRuijs/ECAPA-TDNN | Speaker ID |
| WhisperX | https://github.com/m-bain/whisperX | ASR |

---

## 16. Complete Runtime Output

### 16.1 Full Decision Event

```json
{
  "session_id": "sess_123",
  "timestamp": "2026-04-20T08:12:00Z",
  "device_id": "smart_speaker_02",
  
  "audio": {
    "speaker_segment": {"start": 0.0, "end": 3.5},
    "speaker_id": "usr_abhi",
    "is_trusted": true
  },
  
  "transcription": {
    "text": "remind me to call mom at 7",
    "type": "command",
    "timestamp": 1500.0
  },
  
  "turn_decision": {
    "should_respond": true,
    "state": "shift",
    "confidence": 0.86,
    "reason": ["wake_word", "completed_command"]
  },
  
  "importance": {
    "priority": "medium",
    "is_urgent": false
  },
  
  "response": {
    "mode": "spoken",
    "interrupt_tts": false
  },
  
  "reference_resolution": {
    "resolved": false,
    "note": "no reference to resolve"
  },
  
  "policy": {
    "allowed": true,
    "policy": "balanced",
    "mode": "active_conversation"
  }
}
```

---

**End of Specification**