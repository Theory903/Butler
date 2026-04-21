# Butler Audio Identity + Wake Word + Relation Reasoning Specification

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## Executive Summary

This specification defines Butler's audio identity system for recognizing speakers, detecting wake words, and inferring acoustic relations. The system models audio identity separately from content, using confidence-aware outputs.

### Core Capabilities

- **Wake word detection**: "Butler", "Hey Butler", custom phrases
- **Voice activity detection**: Speech segment isolation
- **Speaker verification**: Is this enrolled user X?
- **Speaker identification**: Among enrolled speakers, who is this?
- **Speaker diarization**: Who spoke when (multi-speaker)
- **Speech recognition**: ASR with timestamps
- **Acoustic event understanding**: Laughter, crying, door slam, baby cry, etc.
- **Relation reasoning**: Speaker-to-device, speaker-to-room, speaker-to-event

### SOTA Stack

| Layer | SOTA Component | Purpose |
|-------|---------------|---------|
| Wake word | openWakeWord | Keyword detection |
| VAD | Silero VAD | Speech detection |
| Speaker embedding | ECAPA-TDNN | Voice identity |
| Diarization | pyannote | Multi-speaker tracking |
| ASR | WhisperX | Transcription + alignment |
| Separation | Asteroid | Source separation |
| Events | Custom classifier | Acoustic events |

### Hard Boundaries

- **Consent-first**: No voice profile without consent
- **Local-processing**: Voice embeddings stay local
- **Soft claims**: Confidence-aware output
- **Enrollment-only**: No random speaker identification
- **Audit logging**: All voice operations logged

---

## 1. System Architecture

### 1.1 Audio Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                 BUTLER AUDIO PIPELINE                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Microphone Array]                                            │
│        │                                                     │
│        ▼                                                     │
│  ┌─────────────┐    ┌─────────────┐                           │
│  │   Wake    │    │    VAD    │                           │
│  │   Word    │───▶│  (Silero)  │                           │
│  │ (openWW)  │    │           │                           │
│  └─────────────┘    └─────┬─────┘                           │
│        │                  │                                 │
│        ▼                  ▼                                 │
│  ┌─────────────────────────────────────┐                │
│  │     Source Separation (Asteroid)     │                │
│  │     - Remove noise, overlap          │                │
│  │     - Isolate target speaker        │                │
│  └──────────────┬──────────────────┘                │
│                 │                                        │
│                 ▼                                        │
│  ┌──────────────┬──────────────────┬──────────────┐   │
│  │  Diarization │  Speaker Embed   │ Acoustic     │   │
│  │  (pyannote)  │  (ECAPA-TDNN)   │ Events      │   │
│  └──────┬──────┴───────┬────────┴──────┬───────┘   │
│         │              │                │             │
│         ▼              ▼                ▼             │
│  ┌─────────────────────────────────────────────┐   │
│  │         Speaker Identity Resolution          │   │
│  │      - Enrolled user → known                 │   │
│  │      - Unknown → speaker track only        │   │
│  └──────────────────┬──────────────────────┘   │
│                     │                                      │
│                     ▼                                      │
│  ┌─────────────────────────────────────────────┐   │
│  │           ASR (WhisperX)                    │   │
│  │      - Transcription + alignment            │   │
│  │      - Timestamps per word                 │   │
│  └──────────────┬──────────────────────┘   │
│                 │                                      │
│                 ▼                                      │
│  ┌─────────────────────────────────────────────┐   │
│  │         Relation Reasoning Layer            │   │
│  │      - SPOKE_IN relation                 │   │
│  │      - USES_SURFACE                      │   │
│  │      - LIKELY_SAME_SPEAKER_AS             │   │
│  │      - NEAR_DEVICE                       │   │
│  └─────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Three Distinct Concepts

Butler separates audio identity into distinct tasks:

| Concept | Task | Output |
|---------|------|--------|
| **Wake-word hit** | Keyword detection | "someone said Butler" |
| **Speaker verification** | Identity check | "is this Abhi?" |
| **Speaker track** | Continuity | "speaker_02 has been talking" |

```
Wake-word hit ≠ Speaker verification ≠ Speaker track
     │                 │              │
     ▼                 ▼              ▼
"trigger"         "who?"         "continuity"
```

---

## 2. Component Specifications

### 2.1 Wake Word Detection

```
┌─────────────────────────────────────────────────────────────┐
│               WAKE WORD DETECTION                           │
├─────────────────────────────────────────────────────────────┤
│ Model: openWakeWord                                         │
│ • Pretrained models: "hey buddy", "ok google" style         │
│ • Custom training: train your own wake word               │
│ • Multi-model support                                   │
│                                                             │
│ Default Phrases:                                           │
│ • "Hey Butler"                                            │
│ • "Butler"                                               │
│ • "Hey Jarvis" (optional)                                │
│                                                             │
│ Configuration:                                            │
│ • Detection threshold: 0.5                               │
│ • False activation filter: 3+ consecutive hits         │
│ • Cooldown period: 2 seconds                            │
│ • Streaming chunks: 16kHz, 16-bit mono                  │
│                                                             │
│ Latency: <50ms for detection                             │
│ Power: <100mW when always-on                            │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Voice Activity Detection

```
┌─────────────────────────────────────────────────────────────┐
│               VOICE ACTIVITY DETECTION                     │
├─────────────────────────────────────────────────────────────┤
│ Model: Silero VAD                                             │
│ • Optimized for fast detection                               │
│ • Sub-millisecond processing on CPU                        │
│ • Stable for unusual / low-quality speech              │
│                                                             │
│ Configuration:                                            │
│ • Speech threshold: 0.5                                  │
│ • Min speech duration: 250ms                              │
│ • Max speech length: 30 seconds                            │
│ • Sample rate: 16kHz (optimized)                          │
│                                                             │
│ Outputs:                                                  │
│ • Speech segments with start/end timestamps            │
│ • Speech probability per chunk                          │
│ • Audio energy levels                                   │
│                                                             │
│ Integration:                                            │
│ • Gate for heavier audio processing                     │
│ • Reduces power, latency, false activations          │
│ • Privacy: only process after wake word              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Speaker Embedding

```
┌─────────────────────────────────────────────────────────────┐
│              SPEAKER EMBEDDING                            │
├─────────────────────────────────────────────────────────────┤
│ Model: ECAPA-TDNN (Emphasized Channel Attention)         │
│ • Text-independent identity recognition              │
│ • 192-dimensional embedding                       │
│ • NVIDIA distribution available                  │
│ • WeSpeaker integration                          │
│ • SpeechBrain integration                        │
│                                                             │
│ Enrollment:                                            │
│ • Minimum 30 seconds of speech                     │
│ • 5+ distinct utterances recommended           │
│ • Re-enrollment after 90 days                    │
│                                                             │
│ Verification:                                          │
│ • Threshold: 0.68 (cosine similarity)            │
│ • FAR goal: <0.01%                                │
│ • FRR target: <3%                                 │
│                                                             │
│ Performance:                                            │
│ • Embedding extraction: ~15ms                        │
│ • Verification: ~5ms                              │
│ • Memory: ~1MB per voiceprint                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 Speaker Diarization

```
┌─────────────────────────────────────────────────────────────┐
│              SPEAKER DIARIZATION                          │
├─────────────────────────────────────────────────────────────┤
│ Model: pyannote                                         │
│ • State-of-the-art diarization                         │
│ • Pretrained pipelines available                    │
│ • NeMo integration available                       │
│                                                             │
│ Output:                                                │
│ �� Speaker segments: who spoke when                  │
│ • Overlap detection                                │
│ • Cluster IDs (not names)                          │
│                                                             │
│ Configuration:                                            │
│ • Max speakers: 10                                  │
│ • Min segment duration: 1 second                  │
│ • Clustering: spectral clustering                 │
│ • Embedding: ECAPA-TDNN                           │
│                                                             │
│ Unknown Speaker Handling:                            │
│ • speaker_00: Unknown adult                           │
│ • speaker_01: Child voice                          │
│ • speaker_02: Guest                             │
│ • Label by characteristics, not guess               │
│                                                             │
│ Integration with Identity:                             │
│ • Diarization creates speaker tracks first          │
│ • Attach identity only when confidence > 0.70     │
│ • Unknown speakers stay as tracks                │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 ASR + Alignment

```
┌─────────────────────────────────────────────────────────────┐
│              ASR + ALIGNMENT                              │
├─────────────────────────────────────────────────────────────┤
│ Model: WhisperX                                             │
│ • Transcription + forced alignment                   │
│ • Integrates with diarization workflows              │
│ • Word-level timestamps                               │
│                                                             │
│ Configuration:                                            │
│ • Model size: base (default), large (SOTA)          │
│ • Language: auto-detect                                │
│ • Timestamp: word-level                                │
│ • Diarization-aware: segments speaker turns          │
│                                                             │
│ Output:                                                   │
│ • Full transcript                                     │
│ • Word-level timestamps                               │
│ • Segment speaker assignments                        │
│ • Confidence per word                                │
│                                                             │
│ Edge Mode:                                               │
│ • Faster-Whisper (small model)                      │
│ • ~30ms per second of audio                         │
│ • Good for command recognition                     │
│                                                             │
│ Premium Mode:                                              │
│ • Whisper large-v2                                    │
│ • ~100ms per second of audio                        │
│ • Better accuracy, especially multi-speaker        │
└─────────────────────────────────────────────────────────────┘
```

### 2.6 Source Separation

```
┌───────────────────────────────────────────────────���─���───────┐
│              SOURCE SEPARATION                          │
├─────────────────────────────────────────────────────────────┤
│ Model: Asteroid                                           │
│ • Open-source source separation                       │
│ • Speech/audio separation research                  │
│                                                             │
│ Use Cases:                                                │
│ • TV overlap in living room                           │
│ • Meeting room overlap                               │
│ • Kitchen noise while talking                     │
│ • Robot in noisy environments                       │
│                                                             │
│ Configuration:                                            │
│ • Number of sources: 2-4                              │
│ • Sampling rate: 16kHz                                │
│ • Chunk processing: 3 seconds                       │
│                                                             │
│ Performance:                                            │
│ • SI-SDR improvement: 10-15 dB                     │
│ • Processing: ~5x realtime on GPU                   │
│ • CPU: feasible with lighter models                  │
│                                                             │
│ Integration:                                            │
│ • Run before diarization when overlap detected      │
│ • Optional: enable via config                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Audio Event Schema

### 3.1 Core Event Types

```python
class AudioEventType(Enum):
    WAKE_WORD_DETECTED = "wake_word_detected"
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    SPEAKER_ENROLLED = "speaker_enrolled"
    SPEAKER_RECOGNIZED = "speaker_recognized"
    COMMAND_DETECTED = "command_detected"
    QUESTION_ASKED = "question_asked"
    
    # Acoustic events
    LAUGHTER = "laughter"
    CRYING = "crying"
    COUGHING = "coughing"
    DOOR_SLAM = "door_slam"
    GLASS_BREAK = "glass_break"
    BABY_CRY = "baby_cry"
    ALARM = "alarm"
    ENGINE = "engine"
    PHONE_RING = "phone_ring"
    KNOCK = "knock"
```

### 3.2 Wake Event

```python
class WakeEvent:
    event_id: str
    wake_phrase: str              # "hey butler"
    confidence: float           # 0.97
    timestamp: datetime
    
    # Audio context
    device_id: str               # "smart_speaker_02"
    room: str                   # "living_room"
    
    # Triggering audio
    audio_energy: float
    duration_ms: int
    
    # Follow-up
    utterance_id: Optional[str]  # linked utterance
    triggered_response: bool
```

### 3.3 Speaker Identity

```python
class SpeakerIdentity:
    speaker_id: str               # "spk_014"
    identity_type: str            # "known" / "unknown"
    
    # For known speakers
    display_name: Optional[str]  # "Abhishek Jha"
    voiceprint_id: Optional[str]
    
    # Method
    method: str                # "ecapa_verification"
    confidence: float          # 0.91
    
    # Enrollment
    enrollment_date: Optional[datetime]
    last_verified: datetime
    utterance_count: int
    
    # Unknown characteristics
    characteristics: Optional[Dict[str, Any]]
    # - "age_range": "adult" / "child"
    # - "gender_hint": "male" / "female"
    # - "tone": "calm" / "energetic"
```

### 3.4 Utterance

```python
class Utterance:
    utterance_id: str
    speaker_id: str
    
    # Transcription
    text: str                  # "remind me to call mom"
    language: str             # "en"
    
    # Timestamps
    start_time: float          # 15234.5 (ms)
    end_time: float           # 15267.8 (ms)
    
    # Word-level alignment
    words: List[Dict[str, Any]]
    # [
    #   {"word": "remind", "start": 15234.5, "end": 15236.2, "confidence": 0.94},
    #   {"word": "me", "start": 15236.5, "end": 15237.8, "confidence": 0.91},
    # ]
    
    # ASR
    asr_model: str            # "whisper-base"
    confidence: float        # 0.89
    
    # Context
    device_id: str
    room: str
    
    # Type classification
    utterance_type: str      # "command" / "question" / "statement"
    intent_classified: Optional[str]
```

### 3.5 Audio Event (Acoustic)

```python
class AcousticEvent:
    event_id: str
    event_type: AudioEventType
    
    # Detection
    timestamp: datetime
    confidence: float       # 0.87
    
    # Source
    device_id: str
    room: str
    
    # Characteristics
    duration_ms: int
    intensity_db: float
    
    # Context
    speaker_co-occurring: Optional[str]
    location_context: Optional[str]
```

---

## 4. Relation Types

### 4.1 Audio Relations

```python
class AudioRelationType(Enum):
    # Speaker relations
    SPOKE_IN = "spoke_in"                    # Speaker in room
    TRIGGERED_WAKE_WORD = "triggered_wake_word"  # Activated device
    LIKELY_SAME_SPEAKER_AS = "likely_same_speaker_as"  # Cross-device identity
    ON_CALL_WITH = "on_call_with"            # Phone call
    
    # Device relations
    USES_SURFACE = "uses_surface"              # Uses smart device
    NEAR_DEVICE = "near_device"            # Physically near
    
    # Event relations
    INTERRUPTED = "interrupted"            # Interrupted someone
    RESPONDED_TO = "responded_to"          # Responded to
    USES_SURFACE = "uses_surface"        # Using media
    
    # Location
    LIKELY_PRESENT_IN_ROOM = "likely_present_in_room"
```

### 4.2 Confidence Rules (Audio)

```
Relation Confidence Rules:

SPOKE_IN(speaker, room):
  - Voice detected in room: +0.3
  - Multiple utterances: +0.2
  - Confirmed by other sensors: +0.25
  - Maximum: 0.85

TRIGGERED_WAKE_WORD(speaker, device):
  - Wake word from device: 1.0 (certain)
  - Within 5 seconds of wake: 0.9
  - Speaker identified: attach confidence

LIKELY_SAME_SPEAKER_AS(speaker_A, speaker_B):
  - Voice embedding cosine > 0.80: +0.5
  - Same device previously: +0.15
  - Same room previously: +0.1
  - Call correlation: +0.15
  - Maximum: 0.88

USES_SURFACE(speaker, device):
  - Direct command to device: +0.4
  - First device use: +0.25
  - Repeated use (3+): +0.3
  - Maximum: 0.92

NEAR_DEVICE(speaker, device):
  - Voice + other sensor (motion): +0.35
  - Voice + BLE proximity: +0.3
  - Voice only: +0.25
  - Maximum: 0.75
```

---

## 5. Memory Graph Schema

### 5.1 Node Types

```python
class AudioNodeType(Enum):
    SPEAKER_IDENTITY = "speaker_identity"
    VOICE_PRINT = "voice_print"
    SPEAKER_TRACK = "speaker_track"
    WAKE_EVENT = "wake_event"
    UTTERANCE = "utterance"
    AUDIO_EVENT = "audio_event"
    DEVICE_MIC = "device_mic"
    CALL_PARTICIPANT = "call_participant"
    ROOM = "room"
    MEDIA_SURFACE = "media_surface"
```

### 5.2 Speaker Entity

```json
{
  "speaker_id": "spk_014",
  "display_name": "Abhishek Jha",
  "node_type": "speaker_identity",
  "voice_print": {
    "embedding_model": "ecapa-tdnn",
    "embedding": [0.12, -0.34, 0.56, ...],
    "enrolled_date": "2026-01-15T10:00:00Z",
    "last_verified": "2026-04-20T08:12:00Z",
    "utterance_count": 847,
    "average_confidence": 0.91
  },
  "characteristics": {
    "age_range": "adult",
    "gender_hint": "male",
    "tone": "energetic",
    "typical_devices": ["smart_speaker_02", "smart_display_01"],
    "typical_rooms": ["living_room", "office"]
  },
  "preferences": {
    "volume_level": 0.7,
    "voice_speed": 1.0,
    "responds_to": ["notifications", "reminders", "calls"]
  }
}
```

### 5.3 Device Entity

```json
{
  "device_id": "smart_speaker_02",
  "node_type": "device_mic",
  "device_type": "smart_speaker",
  "location": {
    "room": "living_room",
    "position": "shelf_near_tv"
  },
  "capabilities": {
    "wake_word": true,
    "vad": true,
    "speaker_recognition": true,
    "asr": true,
    "tts": true,
    "multi_channel": false
  },
  "audio_config": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "pcm_s16le"
  },
  "enrolled_speakers": ["spk_014", "spk_007"]
}
```

### 5.4 Complete Output Format

```json
{
  "timestamp": "2026-04-20T08:12:00Z",
  "device_id": "smart_speaker_02",
  "room": "living_room",
  
  "wake_word": {
    "detected": true,
    "phrase": "hey butler",
    "confidence": 0.97
  },
  
  "speaker_track": "spk_014",
  
  "speaker_identity": {
    "label": "Abhishek Jha",
    "confidence": 0.91,
    "method": "ecapa_verification",
    "is_known": true
  },
  
  "utterance": {
    "text": "remind me to call mom after 7",
    "timestamps": {
      "start": 1234.5,
      "end": 1567.8
    },
    "words": [
      {"word": "remind", "start": 1234.5, "end": 1236.2},
      {"word": "me", "start": 1236.5, "end": 1237.8},
      {"word": "to", "start": 1238.0, "end": 1239.1},
      {"word": "call", "start": 1239.5, "end": 1241.2},
      {"word": "mom", "start": 1241.5, "end": 1243.0},
      {"word": "after", "start": 1243.5, "end": 1245.0},
      {"word": "7", "start": 1245.2, "end": 1246.1}
    ],
    "type": "command",
    "intent": "set_reminder"
  },
  
  "relations": [
    {
      "type": "SPOKE_IN",
      "subject": "spk_014",
      "object": "living_room",
      "confidence": 0.83
    },
    {
      "type": "USES_SURFACE",
      "subject": "spk_014",
      "object": "smart_speaker_02",
      "confidence": 0.79
    }
  ],
  
  "events": []
}
```

### 5.5 Unknown Speaker Output

```json
{
  "speaker_track": "speaker_02",
  "speaker_identity": {
    "label": null,
    "confidence": 0.0,
    "is_known": false,
    "characteristics": {
      "age_range": "child",
      "gender_hint": "unknown"
    }
  },
  "utterance": {
    "text": "can i have ice cream",
    "utterance_type": "question"
  },
  "relations": [
    {
      "type": "LIKELY_PRESENT_IN_ROOM",
      "subject": "speaker_02",
      "object": "kitchen",
      "confidence": 0.72
    }
  ],
  "note": "Unknown child voice - not enrolled"
}
```

---

## 6. Enrollment Flow

### 6.1 User Enrollment

```
┌─────────────────────────────────────────────────────────────┐
│               ENROLLMENT FLOW                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Step 1: Initiate enrollment                                │
│   POST /api/v1/audio/enroll                                │
│   { "display_name": "Abhishek Jha" }                       │
│   → Returns enrollment_id, instructions                    │
│                                                             │
│ Step 2: Collect voice samples                              │
│   • User speaks 5+ different sentences                   │
│   • Total: 30+ seconds of speech                        │
│   • Duration: 2-5 minutes                             │
│   → Upload audio chunks                                  │
│                                                             │
│ Step 3: Generate voiceprint                             │
│   • Extract ECAPA embeddings                           │
│   • Store averaged embedding                            │
│   • Generate voiceprint_id                              │
│                                                             │
│ Step 4: Verification                                     │
│   • User speaks verification phrase                  │
│   • Verify matches enrollment                         │
│   • Store confirmation                                 │
│                                                             │
│ Step 5: Complete                                        │
│   • Return success / failure                           │
│   • Enable speaker recognition                        │
│   • Start personalization                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Enrollment API

```python
# Start enrollment
POST /api/v1/audio/enroll
{
    "display_name": "Abhishek Jha",
    "duration_seconds": 60,
    "consent_given": true
}

# Upload enrollment audio
POST /api/v1/audio/enroll/{enrollment_id}/audio
{
    "audio": "base64_encoded_pcm",
    "sample_rate": 16000
}

# Complete enrollment
POST /api/v1/audio/enroll/{enrollment_id}/complete
{
    "verification_phrase": "my voice is my passport"
}

# Get enrollment status
GET /api/v1/audio/enroll/{enrollment_id}

# Delete enrollment (GDPR)
DELETE /api/v1/audio/enroll/{voiceprint_id}
```

### 6.3 Re-enrollment Triggers

| Trigger | Action |
|---------|--------|
| 90 days since enrollment | Prompt re-enrollment |
| Confidence < 0.6 | Prompt re-enrollment |
| New device added | Adaptive enrollment |
| User request | Immediate re-enrollment |

---

## 7. Deployment Tiers

### 7.1 Tier 1: Always-On Edge ($150-500)

```
Use Case: Home, robot, smart glasses, phone
─────────────────────────────────────────────
Components:
  • Wake word: openWakeWord
  • VAD: Silero VAD
  • Speaker: lightweight ECAPA (20-layer)
  • ASR: Faster-Whisper small
  • Local processing only

Latency:
  • Wake detection: <50ms
  • Speaker verification: <100ms
  • ASR: <500ms

Power:
  • Standby: <50mW
  • Active: <500mW

Storage: 512MB for models
Privacy: 100% local

Supported devices:
  • Raspberry Pi 5 + USB mic
  • Jetson Nano
  • Mobile phone
  • Smart glasses
```

### 7.2 Tier 2: Premium Local/Server ($1.5K-5K)

```
Use Case: Multi-room, office, robotics lab
─────────────────────────────────────────────
Components:
  • Wake word: openWakeWord (full)
  • VAD: Silero VAD (enhanced)
  • Diarization: pyannote 3.0
  • Speaker: ECAPA-TDNN full
  • ASR: WhisperX base
  • Separation: Asteroid (optional)

Latency:
  • Wake detection: <30ms
  • Diarization: <1s per minute
  • Speaker verification: <50ms
  • ASR: <300ms

Processing: Local server
Storage: 4GB for models + embeddings

Features:
  • Multi-speaker handling
  • Cross-device continuity
  • Acoustic events
  • Room awareness
```

### 7.3 Tier 3: Research / SOTA Premium ($15K+)

```
Use Case: Campus, call center, production
─────────────────────────────────────────────
Components:
  • Ensemble wake words
  • Enhanced VAD
  • pyannote + NeMo diarization
  • ECAPA + speakerNet ensemble
  • WhisperX large
  • Full Asteroid pipeline
  • Cross-device correlation
  • Room-aware multi-mic

Latency:
  • Wake: <20ms
  • Diarization: <500ms per minute
  • Full pipeline: <2s

Processing: GPU cluster
Storage: 20GB+ models

Features:
  • Call + ambient correlation
  • Wearable audio correlation
  • Multi-room fusion
  • Active learning
  • Research APIs
```

### 7.4 Tier Comparison

| Feature | Tier 1 | Tier 2 | Tier 3 |
|---------|-------|-------|-------|
| Wake word | ✓ | ✓ | ✓ |
| VAD | ✓ | ✓ | ✓ |
| Diarization | ✗ | ✓ | ✓ |
| Speaker ID | Basic | Full | Ensemble |
| ASR | Fast | Base | Large |
| Separation | ✗ | ✓ | ✓ |
| Events | ✗ | Basic | Full |
| Multi-room | ✗ | ✓ | ✓ |
| Call correlation | ✗ | ✗ | ✓ |
| Latency | <500ms | <2s | <2s |
| Cost | $150 | $1.5K | $15K |

---

## 8. Database Schema

### 8.1 Speaker Table

```sql
CREATE TABLE audio_speakers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name VARCHAR(255) NOT NULL,
    voiceprint_id VARCHAR(100) UNIQUE,
    
    -- Voice embedding
    voice_embedding VECTOR(192),
    
    -- Enrollment
    enrolled_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_verified TIMESTAMP WITH TIME ZONE,
    utterance_count INTEGER DEFAULT 0,
    average_confidence FLOAT,
    
    -- Consent
    consent_given BOOLEAN DEFAULT FALSE,
    consent_date TIMESTAMP WITH TIME ZONE,
    retention_policy VARCHAR(50) DEFAULT 'yearly',
    
    -- Characteristics
    age_range VARCHAR(20),
    gender_hint VARCHAR(20),
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_speakers_voiceprint ON audio_speakers(voiceprint_id);
CREATE INDEX idx_speakers_embedding ON audio_speakers USING ivfflat (voice_embedding vector_cosine_ops);
CREATE INDEX idx_speakers_consent ON audio_speakers(consent_given) WHERE consent_given = TRUE;
```

### 8.2 Utterances Table

```sql
CREATE TABLE audio_utterances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    speaker_id UUID REFERENCES audio_speakers(id),
    
    -- Transcription
    text TEXT NOT NULL,
    language VARCHAR(10),
    
    -- Timestamps
    start_time FLOAT,
    end_time FLOAT,
    
    -- Word alignment (JSONB)
    words JSONB,
    
    -- ASR
    asr_model VARCHAR(50),
    confidence_score FLOAT,
    
    -- Context
    device_id VARCHAR(100),
    room VARCHAR(100),
    
    -- Classification
    utterance_type VARCHAR(50),
    intent_classified VARCHAR(100),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_utterances_speaker ON audio_utterances(speaker_id);
CREATE INDEX idx_utterances_timestamp ON audio_utterances(created_at DESC);
CREATE INDEX idx_utterances_device ON audio_utterances(device_id);
```

### 8.3 Relations Table

```sql
CREATE TABLE audio_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES audio_speakers(id),
    target_id VARCHAR(100) NOT NULL,
    relation_type VARCHAR(50) NOT NULL,
    
    confidence_score FLOAT NOT NULL,
    evidence JSONB,
    
    first_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE (source_id, target_id, relation_type)
);

CREATE INDEX idx_relations_source ON audio_relations(source_id);
CREATE INDEX idx_relations_confidence ON audio_relations(confidence_score DESC);
```

### 8.4 Acoustic Events Table

```sql
CREATE TABLE acoustic_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Source
    device_id VARCHAR(100) NOT NULL,
    room VARCHAR(100),
    
    -- Detection
    confidence_score FLOAT,
    duration_ms INTEGER,
    intensity_db FLOAT,
    
    -- Context
    speaker_cooccurring UUID REFERENCES audio_speakers(id),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_acoustic_timestamp ON acoustic_events(timestamp DESC);
CREATE INDEX idx_acoustic_type ON acoustic_events(event_type);
CREATE INDEX idx_acoustic_room ON acoustic_events(room);
```

---

## 9. API Reference

### 9.1 Wake & Recognition API

```python
# Process audio (after wake word)
POST /api/v1/audio/process
{
    "audio": "base64_encoded_pcm",
    "device_id": "smart_speaker_02",
    "include_transcript": true,
    "include_relations": true
}

# Verify speaker
POST /api/v1/audio/verify
{
    "audio": "base64_encoded_pcm",
    "speaker_id": "spk_014"
}

# Identify speaker (among enrolled)
POST /api/v1/audio/identify
{
    "audio": "base64_encoded_pcm"
}

# Get speaker profile
GET /api/v1/audio/speakers/{speaker_id}

# Get speaker history
GET /api/v1/audio/speakers/{speaker_id}/utterances?from=2026-04-01
```

### 9.2 Room & Device API

```python
# Get room activity
GET /api/v1/audio/rooms/living_room/activity?from=2026-04-20T08:00

# Get device interactions
GET /api/v1/audio/devices/smart_speaker_02/interactions?limit=50

# Get acoustic events
GET /api/v1/audio/events?type=baby_cry&from=2026-04-01
```

### 9.3 Configuration API

```python
# Update wake phrases
PUT /api/v1/audio/config/wake_phrases
{
    "phrases": ["hey butler", "butler", "ok butler"],
    "threshold": 0.5
}

# Update thresholds
PUT /api/v1/audio/config/thresholds
{
    "speaker_verification": 0.68,
    "diarization_confidence": 0.70,
    "asr_confidence": 0.75
}
```

---

## 10. Error Handling

### 10.1 RFC 9457 Errors

```json
{
  "type": "https://butler.local/v1/problems/speaker-not-enrolled",
  "title": "Speaker Not Enrolled",
  "status": 404,
  "detail": "No voice print found for speaker 'unknown_voice'",
  "instance": "/api/v1/audio/verify"
}

{
  "type": "https://butler.local/v1/problems/consent-required",
  "title": "Consent Required",
  "status": 403,
  "detail": "Speaker verification requires consent",
  "instance": "/api/v1/audio/verify"
}

{
  "type": "https://butler.local/v1/problems/enrollment-expired",
  "title": "Enrollment Expired",
  "status": 410,
  "detail": "Voice print expired - re-enrollment required",
  "instance": "/api/v1/audio/identify"
}
```

### 10.2 Error Types

| Type | Code | Description |
|------|------|-------------|
| `speaker-not-enrolled` | 404 | Voice print not found |
| `consent-required` | 403 | Consent needed |
| `enrollment-expired` | 410 | Re-enrollment needed |
| `no-speech-detected` | 200 | No speech (success, empty) |
| `transcription-failed` | 500 | ASR failed |
| `device-offline` | 503 | Mic unavailable |

---

## 11. Safety and Privacy

### 11.1 Consent Requirements

| Action | Consent Required |
|--------|---------------|
| Store voice embedding | Explicit yes |
| Identify by name | Enrolled + consent |
| Cross-device tracking | Opt-in |
| Call recording | Explicit yes |
| Share with 3rd party | Explicit no |

### 11.2 Retention Policies

```python
class AudioRetentionPolicy(Enum):
    SESSION_ONLY = "session"    # Not stored
    DAILY = "daily"          # 24 hours
    WEEKLY = "weekly"        # 7 days
    MONTHLY = "monthly"      # 30 days
    YEARLY = "yearly"        # 365 days
    FOREVER = "forever"      # Until deleted
```

### 11.3 Safety Rules

```
┌─────────────────────────────────────────────────────────────┐
│                    HARD BOUNDARIES                       │
├─────────────────────────────────────────────────────────────┤
│ ❌ Voice profiling without consent                     │
│ ❌ Silent biometric collection                      │
│ ❌ Random speaker identification                   │
│ ❌ Recording without disclosure                    │
│ ❌ Cross-device tracking without opt-in            │
│ ❌ Retention without policy                        │
│ ❌ Sharing with 3rd parties                        │
└─────────────────────────────────────────────────────────────┘
```

### 11.4 Local-First Principles

1. **Process locally**: Voice embeddings never leave device
2. **Wake-word gate**: Only process after wake trigger
3. **Retention limits**: Auto-expire after policy duration
4. **Consent-first**: No voice stored without consent
5. **Audit everything**: Log all voice operations

---

## 12. Latency Budgets

### 12.1 Per-Tier Latency

| Operation | Tier 1 | Tier 2 | Tier 3 |
|------------|-------|-------|-------|
| Wake detection | <50ms | <30ms | <20ms |
| VAD | <5ms | <3ms | <2ms |
| Speaker verification | <100ms | <50ms | <30ms |
| Full identification | <200ms | <100ms | <75ms |
| Diarization | N/A | <1s | <500ms |
| ASR (per second audio) | <500ms | <300ms | <200ms |
| **Total (command)** | **<500ms** | **<500ms** | **<300ms** |
| **Total (1min recording)** | **<30s** | **<10s** | **<5s** |

---

## 13. Model References

### 13.1 SOTA Models

| Model | Repository | Purpose |
|-------|-----------|---------|
| openWakeWord | https://github.com/dscripka/openWakeWord | Wake word |
| Silero VAD | https://github.com/snakers4/silero-vad | VAD |
| ECAPA-TDNN | https://github.com/TaoRuijs/ECAPA-TDNN | Speaker embedding |
| pyannote | https://github.com/pyannote/pyannote-audio | Diarization |
| WhisperX | https://github.com/m-bain/whisperX | ASR + alignment |
| Asteroid | https://github.com/asteroid-team/asteroid | Source separation |
| WeSpeaker | https://github.com/wenet-e2e/WeSpeaker | Speaker recognition |
| SpeechBrain | https://github.com/speechbrain/speechbrain | Speaker verification |

### 13.2 Configuration

```
# Tier 1: Local Edge
wake_word:
  model: openww-small
  threshold: 0.5
  phrases: ["hey butler", "butler"]

vad:
  model: silero
  threshold: 0.5

speaker:
  model: ecapa-tdnn-light
  verification_threshold: 0.68

asr:
  model: faster-whisper-small
  language: auto

# Tier 2: Premium
speaker:
  model: ecapa-tdnn-full
  verification_threshold: 0.70

diarization:
  model: pyannote/3.0
  max_speakers: 10

asr:
  model: whisper-base

separation:
  model: asteroid/convtasnet
  sources: 2

# Tier 3: SOTA
speaker:
  model: ensemble [ecapa, speechbrain]
  verification_threshold: 0.72

diarization:
  model: pyannote/3.0-neural

asr:
  model: whisper-large-v2
```

---

## 14. Output Examples

### 14.1 Command Recognition

```json
{
  "wake_word": {"detected": true, "phrase": "hey butler", "confidence": 0.97},
  "speaker_identity": {"label": "Abhishek Jha", "confidence": 0.91},
  "utterance": {
    "text": "turn off the living room lights",
    "type": "command",
    "intent": "device_control"
  },
  "relations": [
    {"type": "USES_SURFACE", "object": "smart_speaker_02", "confidence": 0.79},
    {"type": "SPOKE_IN", "object": "living_room", "confidence": 0.83}
  ]
}
```

### 14.2 Multi-Speaker Meeting

```json
{
  "timestamp": "2026-04-20T10:00:00Z",
  "device_id": "conference_mic_array",
  "room": "conference_room",
  
  "speaker_tracks": [
    {
      "speaker_id": "speaker_00",
      "display_name": "Abhishek Jha",
      "segments": [
        {"start": 0.0, "end": 45.2, "confidence": 0.94},
        {"start": 120.5, "end": 180.3, "confidence": 0.89}
      ]
    },
    {
      "speaker_id": "speaker_01",
      "display_name": "Sarah Chen",
      "segments": [
        {"start": 45.5, "end": 118.0, "confidence": 0.91}
      ]
    },
    {
      "speaker_id": "speaker_02",
      "display_name": null,
      "segments": [
        {"start": 182.0, "end": 240.0, "confidence": 0.0}
      ],
      "note": "Unknown speaker"
    }
  ],
  
  "transcript": [
    {"speaker": "Abhishek Jha", "text": "Let's discuss the Q2 roadmap...", "start": 0.0},
    {"speaker": "Sarah Chen", "text": "I have some concerns about...", "start": 45.5},
    {"speaker": "speaker_02", "text": "What about the timeline?", "start": 182.0}
  ],
  
  "relations": [
    {"type": "ON_CALL_WITH", "subject": "speaker_00", "object": "speaker_01", "confidence": 0.87}
  ]
}
```

### 14.3 Acoustic Event

```json
{
  "event_type": "baby_cry",
  "timestamp": "2026-04-20T03:00:00Z",
  "device_id": "baby_monitor_01",
  "room": "nursery",
  
  "detection": {
    "confidence": 0.89,
    "duration_ms": 45000,
    "intensity_db": 72
  },
  
  "context": {
    "time_of_day": "night",
    "likely_child": true
  },
  
  "relations": [
    {"type": "LIKELY_PRESENT_IN_ROOM", "object": "nursery", "confidence": 0.85}
  ],
  
  "alerts": [
    {"type": "notification", "target": "parents", "message": "Baby crying in nursery"}
  ]
}
```

---

## 15. Integration Points

### 15.1 With Vision System

| Audio Event | Vision Event | Combined Understanding |
|------------|-------------|---------------------|
| Speaker in living room | Person in living room | ✅ Confirmed presence |
| Unknown voice near door | Unknown person at door | ✅ Visitor alert |
| Baby cry | Baby in nursery | ✅ Event confirmed |
| Command to TV | TV playing | ✅ Context aware |

### 15.2 With Butler Services

```
Speaker recognized → User preferences loaded
  → Volume level applied
  → Response style applied
  → Notification preferences applied

Acoustic event → Event classification
  → Priority assessment
  → Alert routing
  → Documentation

Command detected → Intent classification
  → Orchestrator handoff
  → Tool execution
```

---

## 16. Hard Boundaries

### 16.1 Consent Requirements

| Action | Consent Required |
|--------|---------------|
| Store voice embedding | Explicit yes |
| Recognize by voice | Enrolled + consent |
| Track across devices | Opt-in |
| Record conversations | Explicit yes |
| Share with 3rd party | Explicit no by default |

### 16.2 Privacy Rules

```
┌─────────────────────────────────────────────────────────────┐
│                    HARD BOUNDARIES                       │
├─────────────────────────────────────────────────────────────┤
│ ❌ Voice profiling without consent                     │
│ ❌ Silent biometric collection                      │
│ ❌ Random speaker identification                   │
│ ❌ Recording/storage without disclosure          │
│ ❌ Cross-device tracking without opt-in            │
│ ❌ Retention without policy                        │
│ ❌ Sharing with 3rd parties                        │
│ ❌ Surveillance mode                               │
└─────────────────────────────────────────────────────────────┘
```

### 16.3 Local-First Guarantees

1. **Process locally** - Voice embeddings never leave device
2. **Wake-word gate** - Only process after wake trigger
3. **Retention limits** - Auto-expire after policy duration
4. **Consent-first** - No voice stored without consent
5. **Audit logging** - Log all voice operations

---

**End of Specification**