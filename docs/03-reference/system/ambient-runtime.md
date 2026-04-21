# Ambient Runtime System
> **Version:** 2.0 (Oracle-Grade)
> **Updated:** 2026-04-20
> **Status:** Production Ready
> **Target Latency:** <500ms end-to-end
> **Sources:** Natively, OpenClaw, Butler v2.0 standards

---

## Overview

Butler Ambient Runtime is the always-on perception layer that operates in the background with zero user interaction. This system implements patterns from Natively and OpenClaw research, optimized for privacy, latency, and sovereignty.

---

## Voice System

### Wake Word Detection

| Platform | Implementation | Latency |
|----------|----------------|---------|
| macOS/iOS | CoreSpeech on-device | <100ms |
| Android | OpenWakeWord + TensorFlow Lite | <150ms |
| Linux | Porcupine | <120ms |

- **Wake Word:** "Hey Butler" (default, user configurable)
- **False Accept Rate:** < 1 per 1000 hours
- **Always runs on-device, never leaves the device**
- No cloud calls for wake detection

### Talk Mode

Three operational modes:
1. **Push-to-talk** - Explicit user activation
2. **Continuous voice** (Android only) - Always listening after wake
3. **Ambient mode** - Passive context capture with explicit consent

### Dual Audio Channels

**CRITICAL PATTERN FROM NATIVELY RESEARCH**

Two completely isolated audio pipelines:
1. **System Audio Capture**
   - Rust native zero-copy ABI
   - Captures output audio stream
   - No microphone access required
   - Sample rate: 16kHz mono
   - Buffer size: 10ms

2. **Microphone Capture**
   - Separate hardware channel
   - WebRTC ML VAD (Voice Activity Detection)
   - Adaptive RMS silence detection
   - Automatic gain control
   - Noise suppression

**Channel Isolation Guarantees:**
- No cross-talk between pipelines
- Independent consent controls
- Separate memory domains
- Zero shared buffers

### STT/TTS Pipeline

Dual stack implementation from OpenClaw:

| Layer | Primary | Fallback |
|-------|---------|----------|
| STT | ElevenLabs Streaming | System native STT |
| TTS | ElevenLabs Turbo | System TTS |
| Diarization | pyannote.audio | OpenAI Whisper |

**Pipeline Guarantees:**
- <500ms end-to-end latency target
- Sliding-window RAG with 50-token overlap
- Incremental transcription
- Speaker diarization for multi-party conversations
- Automatic punctuation and capitalization

---

## Canvas/A2UI

### Rendering Engine

Ambient UI overlay system:
- Hardware accelerated rendering
- 60fps target refresh rate
- Transparency support
- System-level window ordering
- No input capture unless explicitly granted

### Real-time Updates

- Delta updates only (no full redraws)
- 16ms frame budget
- Backpressure handling
- Automatic throttling when system is under load

---

## Ambient Context

### Screen Capture

- Opt-in only with explicit consent
- Per-application filtering
- OCR on-device only
- No raw pixel data stored
- Automatic redaction of sensitive fields

### Camera Access

- Frame-by-frame consent
- On-device ML processing only
- No frames leave the device
- Automatic face blurring
- Motion detection only

### Location

- Geohash precision control
- Background location throttling
- No precise location unless explicitly requested
- Fuzzing for privacy

### Media

- Metadata only capture
- No media content extraction
- Playback state tracking
- Automatic pause/resume detection

---

## Privacy & Security

### Consent Model

**MANDATORY FOR ALL AMBIENT CAPTURE**

1. **Explicit opt-in required** for every capability
2. **Granular per-feature controls**
3. **Revocable at any time**
4. **Audit log of all access**
5. **No silent enablement**

Consent states:
- `DENIED` - No access
- `GRANTED_ONCE` - Single use only
- `GRANTED_TEMPORARY` - Time limited
- `GRANTED_PERMANENT` - Persistent (user can revoke)

### Data Classification

All ambient data is classified:

| Class | Retention | Encryption | Sharing |
|-------|-----------|------------|---------|
| PUBLIC | 30 days | AES-256 | Allowed |
| INTERNAL | 7 days | AES-256 | Internal only |
| SENSITIVE | 24 hours | AES-256-GCM | Never shared |
| RESTRICTED | 1 hour | Client-side only | Never leaves device |

### Retention Policies

- Automatic deletion after retention period
- No backups of ambient data
- User initiated purge available at any time
- Wipe on logout
- Secure deletion with overwriting

### Memory Sovereignty

- All ambient context stored locally first
- Cloud sync is opt-in only
- User owns all data
- No training on user data without explicit consent
- Export and deletion rights fully respected

### Multi-tenant Isolation

- Separate memory domains per user
- No cross-user data leakage
- Hardware enforced isolation where available
- Process masquerading for stealth mode operation
- No shared state between sessions

---

## Performance Guarantees

| Metric | Target |
|--------|--------|
| End-to-end latency | <500ms |
| CPU usage idle | <1% |
| CPU usage active | <5% |
| Memory footprint | <128MB |
| Battery impact | <2% per hour |

---

## Health States

Four-state health model (Oracle v2.0 standard):

| State | Description |
|-------|-------------|
| `STARTING` | Initializing pipelines, loading models |
| `HEALTHY` | All systems operational, meeting latency targets |
| `DEGRADED` | Operating with fallback providers, latency >500ms |
| `UNHEALTHY` | Critical failure, ambient capture disabled |

---

## Anti-Patterns

❌ **DO NOT:**
- Enable ambient capture without explicit consent
- Store raw audio or video data
- Send ambient data to cloud without user approval
- Use ambient context for advertising or profiling
- Run at higher priority than foreground applications

✅ **ALWAYS:**
- Respect user privacy preferences
- Minimize resource usage
- Fail open (disable capture on error)
- Audit all access
- Provide full transparency

---

*This document implements all patterns from Natively and OpenClaw research, adapted for Butler's sovereignty and privacy requirements.*
