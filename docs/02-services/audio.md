# Audio Service - Technical Specification

> **For:** Engineering  
> **Status:** Partial-Active (v3.1) — STT/TTS operational with three-tier fallback; diarization/music pending
> **Version:** 3.1
> **Reference:** Butler stacked audio system with dual-STT, diarization, and multimodal fusion  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **AudioModelProxy** | ✅ IMPLEMENTED | Three-tier fallback: GPU worker → OpenAI Whisper/TTS → dev mock |
| 2 | **STT (Fast Path)** | ✅ IMPLEMENTED | Parakeet-TDT-0.6B via GPU worker; OpenAI Whisper-1 cloud fallback |
| 3 | **STT (Accurate Path)** | ✅ IMPLEMENTED | Whisper-Large-V3 via GPU worker; confidence-gated upgrade |
| 4 | **TTS** | ✅ IMPLEMENTED | Coqui/Piper via GPU worker; OpenAI TTS-1 cloud fallback |
| 5 | **Speaker Diarization** | 🔲 STUB | pyannote/heartbeat endpoint (GPU worker integration pending) |
| 6 | **Music Identification** | 🔲 STUB | AcoustID API integration structure present, not wired |
| 7 | **Rich Speech Analysis** | 🔲 STUB | Emotion/language detection endpoints not yet implemented |

---

## 0.1 v3.1 Implementation Notes

> **Completed in v3.1 (2026-04-19)**

### Three-Tier Fallback (`services/audio/models.py`)
`AudioModelProxy` now implements a self-healing fallback chain:

```
Tier 1  Local GPU worker    (AUDIO_GPU_ENDPOINT — self-hosted Parakeet/Whisper/XTTS)
   ↓ on ConnectError / HTTP error
Tier 2  OpenAI Whisper API  (STT) / OpenAI TTS-1 (gated by OPENAI_API_KEY)
   ↓ on API error / key absent
Tier 3  Dev mock            (only when ENVIRONMENT == development)
   ↓ still fails
RuntimeError raised (production only)
```

- **STT**: `POST /stt` to GPU worker; falls back to `openai/whisper-1` transcription API
- **TTS**: `POST /tts` to GPU worker; falls back to `openai/tts-1` (voice: `nova`)
- **Voice Cloning**: Consent policy enforced in `TTSManager` before any GPU call

### What is NOT Yet Implemented
- Diarization (`pyannote/heartbeat`) — GPU worker endpoint not wired
- Music identification — AcoustID key present in settings but endpoint not called
- Streaming STT — WebSocket path to GPU worker not yet implemented

### Key Files
| File | Role |
|------|------|
| `services/audio/models.py` | `AudioModelProxy` with three-tier fallback **[UPGRADED v3.1]** |
| `services/audio/stt.py` | Dual-STT strategy (Fast/Accurate routing) |
| `services/audio/tts.py` | TTS with consent policy enforcement |
| `services/audio/service.py` | Audio service facade |

---

### 1.1 Purpose
The Audio service handles **speech and audio processing** via a stacked audio system:
- Speech-to-Text (STT) - primary and fallback
- Speaker diarization
- Rich speech understanding
- Text-to-Speech (TTS)
- Music identification

This is NOT "send audio to Whisper and hope." It's a system where each model does one job, with dual-STT strategy for latency vs accuracy, speaker segmentation for meeting understanding, and proper quality controls.

### 1.2 Stacked Audio Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Butler Stacked Audio Perception                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: Microphone / Audio File / Stream                                  │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 1: Preprocessing                                      │   │
│  │  • VAD / voice activity detection                        │   │
│  │  • Noise reduction / denoising                         │   │
│  │  • Format conversion                                 │   │
│  │  • Chunking for streaming                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 2: STT Strategy                                      │   │
│  │                                                                  │   │
│  │  ┌──────────────┐   ┌──────────────┐                          │   │
│  │  │  Whisper    │   │  Parakeet   │                          │   │
│  │  │  large-v3   │   │  TDT 0.6B  │                          │   │
│  │  │ (multilang) │   │ (English+)  │                          │   │
│  │  └──────────────┘   └──────────────┘                          │   │
│  │                                                                  │   │
│  │  Strategy: Fast pass → High-accuracy pass if needed        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 3: Speech Intelligence                                     │   │
│  │                                                                  │   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │   │
│  │  │ pyannote   │   │ Voice ID     │   │ SenseVoice  │          │   │
│  │  │ diarization│   │(Identification)│   │ richer     │          │   │
│  │  │           │   │              │   │ understndg  │          │   │
│  │  └──────────────┘   └──────────────┘   └──────────────┘          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ TTS OUTPUT (Separate Layer)                                  │   │
│  │  • Coqui TTS / XTTS-v2                                       │   │
│  │  • Voice cloning with consent mechanism                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Boundaries

| Service | Boundary |
|---------|----------|
| Audio | Perception + synthesis only |
| Orchestrator | Decides when to process audio |
| Memory | Stores transcripts with retention |
| Communication | Uses for voice response with TTS |

### 1.4 Hermes Library Integration
Audio is **fully integrated**. Hermes preserves audio tooling for future library inventory and multimodal fusion.

---

## 2. Dual-STT Strategy

### 2.1 Primary vs Fallback

| Model | Use Case | Latency | Languages | Quality |
|-------|----------|---------|----------|---------|
| **Whisper large-v3** | Multilingual | <3s | 100+ | Base |
| **whisper.cpp** | Local/low-resource | <2s | 100+ | Good |
| **Parakeet TDT 0.6B** | English-first premium | <500ms | Best (English) |
| **Parakeet LT** | Fast local | <200ms | Good (English) |

### 2.2 Two-Pass Strategy

```python
class DualSTTStrategy:
    """Fast pass → accuracy pass if needed"""
    
    async def transcribe(
        self, 
        audio: bytes,
        language: str = None,
        quality_mode: str = "auto"  # fast, balanced, accurate
    ) -> TranscribeResult:
        
        # Choose strategy based on quality_mode
        if quality_mode == "fast":
            # Single pass with fast model
            return await self.fast_pass(audio, language)
        
        elif quality_mode == "balanced":
            # Fast pass for speed, check confidence
            result = await self.fast_pass(audio, language)
            
            if result.confidence < 0.85:
                # Fallback to accurate pass
                accurate = await self.accurate_pass(audio, language)
                accurate.was_upgraded = True
                return accurate
            
            return result
        
        else:  # accurate - skip fast pass
            return await self.accurate_pass(audio, language)
    
    async def fast_pass(self, audio: bytes, language: str) -> TranscribeResult:
        """Whisper base or Parakeet LT"""
        model = "parakeet-lt" if language == "en" else "whisper-base"
        return await self.run_stt(audio, model)
    
    async def accurate_pass(self, audio: bytes, language: str) -> TranscribeResult:
        """Whisper large-v3 or Parakeet TDT"""
        model = "parakeet-tdt" if language == "en" else "whisper-large-v3"
        return await self.run_stt(audio, model)

@dataclass
class TranscribeResult:
    text: str
    confidence: float
    words: list[WordInfo]
    language: str
    model_used: str
    was_upgraded: bool = False
    processing_time_ms: int
```

---

## 3. Speaker Diarization (pyannote.audio)

### 3.1 Diarization for Meetings

```python
class SpeakerDiarization:
    """Who's speaking when - critical for meetings"""
    
    async def diarize(
        self,
        audio: bytes,
        min_speakers: int = 1,
        max_speakers: int = 10
    ) -> DiarizationResult:
        """Use pyannote.audio for speaker segmentation"""
        
        # Run diarization
        segments = await self.pyannote.diarize(
            audio,
            min_speakers=min_speakers,
            max_speakers=max_speakers
        )
        
        # Group by speaker
        speakerSegments = self.group_by_speaker(segments)
        
        return DiarizationResult(
            segments=segments,
            speaker_count=len(speakerSegments),
            segments_by_speaker=speakerSegments
        )

@dataclass
class DiarizationResult:
    segments: list[SpeakerSegment]
    speaker_count: int
    segments_by_speaker: dict[str, list[SpeakerSegment]]
    
@dataclass
class SpeakerSegment:
    speaker_id: str  # "SPEAKER_00", "SPEAKER_01"
    start: float
    end: float
    confidence: float
    text: str = None  # Filled after STT
```

### 3.2 Meeting Flow

```python
async def process_meeting(audio: bytes) -> MeetingTranscript:
    # 1. Diarize first
    diarization = await self.diarize.diarize(audio)
    
    # 2. transcribe each segment separately
    full_transcript = []
    for segment in diarization.segments:
        segment_audio = self.extract(audio, segment.start, segment.end)
        result = await self.stt.transcribe(segment_audio)
        
        full_transcript.append(JoinedSegment(
            speaker_id=segment.speaker_id,
            start=segment.start,
            end=segment.end,
            text=result.text,
            confidence=result.confidence
        ))
    
    return MeetingTranscript(segments=full_transcript)
```

---

## 4. Speaker Identification (Voice ID)

### 4.1 Enrollment & Matching
Beyond diarization ("Who is Speaker 1?"), Voice ID determines "Is Speaker 1 Abhishek?".

```python
class VoiceIdentityManager:
    """Matches embeddings against enrolled profiles"""
    
    async def identify_speaker(
        self,
        audio_chunk: bytes,
        threshold: float = 0.75
    ) -> Optional[str]:
        # 1. Extract embedding via GPU worker
        embedding = await self.proxy.extract_embedding(audio_chunk)
        
        # 2. Vector match against database
        # (Cosine similarity search)
        match = await self.db.search_voice_profiles(embedding)
        
        if match.score >= threshold:
            return match.account_id
        return None
```

---

## 5. Rich Speech Understanding (SenseVoice)

### 4.1 Beyond Basic STT

```python
class SenseVoiceUnderstanding:
    """Emotion, language ID, event detection"""
    
    async def analyze(
        self,
        audio: bytes
    ) -> SpeechAnalysis:
        """Use SenseVoice for richer understanding"""
        
        result = await self.sensevoice.analyze(audio)
        
        return SpeechAnalysis(
            language=result.language,  # Detected language
            language_confidence=result.language_confidence,
            emotion=result.emotion,  # happy, sad, angry, neutral
            emotion_confidence=result.emotion_confidence,
            audio_event=result.audio_event,  # applause, laughter, etc.
            text=result.text  # Also provides transcription
        )

# Use as enhancement layer, NOT replacement for primary STT
```

---

## 5. Text-to-Speech

### 5.1 TTS Stack

| Model | Use Case | Latency | Voice Cloning |
|-------|----------|---------|--------------|
| **Coqui TTS** | Default open | <2s | XTTS-v2 (consent) |
| **XTTS-v2** | Voice cloning | <3s | Yes (consent req) |
| **System TTS** | Edge fallback | <100ms | No |

### 5.2 Voice Cloning Policy

```python
class TTSManager:
    """Voice cloning with explicit consent"""
    
    VOICE_CLoning_POLICY = """
    - Voice cloning requires EXPLICIT user consent
    - Cloned voice stored with encryption
    - Usage logged for audit
    - User can revoke and request deletion
    """
    
    async def generate_with_voice(
        self,
        text: str,
        voice_reference: str = None,  # User's stored voice
        consent_verified: bool = False
    ) -> TTSResult:
        
        if voice_reference and not consent_verified:
            raise PermissionError("Voice cloning requires consent")
        
        if voice_reference:
            result = await self.xtts.generate(
                text=text,
                voice_ref=voice_reference
            )
        else:
            result = await self.coqui.generate(text=text)
        
        return result
```

---

## 6. Music Identification

### 6.1 Chromaprint + AcoustID

```python
class MusicIdentifier:
    """Shazam-like functionality"""
    
    async def identify(
        self,
        audio: bytes
    ) -> MusicMatch:
        """Identify song from audio fingerprint"""
        
        # Extract fingerprint
        fingerprint = await self.chromaprint.extract(audio)
        
        # Query AcoustID
        result = await self.acoustid.lookup(fingerprint)
        
        return MusicMatch(
            title=result.title,
            artist=result.artist,
            duration=result.duration,
            score=result.score,  # Match confidence
            release=result.release
        )
```

**Limitation:** Chromaprint is for near-identical audio, NOT general audio understanding.

---

## 7. Streaming Mode

### 7.1 Streaming STT

```python
class StreamingSTT:
    """Real-time transcription"""
    
    async def start_stream(
        self,
        language: str = "en",
        endpointing_ms: int = 500
    ) -> StreamSession:
        
        return StreamSession(
            session_id=uuid4(),
            language=language,
            endpointing_timeout=endpointing_ms,
            buffer=[]
        )
    
    async def process_chunk(
        self,
        session: StreamSession,
        audio_chunk: bytes
    ) -> StreamUpdate:
        
        # Add to buffer
        session.buffer.append(audio_chunk)
        
        # Check for endpoint (silence or timeout)
        if await self.is_endpoint(session):
            # Flush to STT
            result = await self.stt.transcribe(
                b"".join(session.buffer)
            )
            
            session.buffer = []  # Reset
            
            return StreamUpdate(
                transcript=result.text,
                confidence=result.confidence,
                finalized=True
            )
        
        return StreamUpdate(finalized=False)

# WebSocket interface
WS /audio/stream
  Client: { "type": "audio", "data": "base64" }
  Server: { "type": "partial", "transcript": "..." }
  Server: { "type": "final", "transcript": "...", "confidence": 0.95, "speaker_id": "USER:..." }
```

---

## 8. Voice Activity Detection

### 8.1 VAD

```python
class VoiceActivityDetector:
    """Filter silence from audio"""
    
    async def detect_speech(
        self,
        audio: bytes,
        threshold: float = 0.5,
        min_speech_ms: int = 250
    ) -> VADResult:
        
        segments = await self.webrtc_vad.process(
            audio,
            threshold=threshold,
            min_speech_duration=min_speech_ms / 1000
        )
        
        return VADResult(
            has_speech=len(segments) > 0,
            speech_segments=segments
        )
```

---

## 9. Preprocessing

### 9.1 Audio Preprocessor

```python
class AudioPreprocessor:
    async def process(self, audio: bytes) -> ProcessedAudio:
        # 1. Format detection and conversion
        audio = await self.convert_to_wav(audio)
        
        # 2. Resample to 16kHz (STT optimal)
        audio = await self.resample(audio, 16000)
        
        # 3. Normalize volume
        audio = await self.normalize(audio, target_db=-20)
        
        # 4. Remove silence
        audio = await self.remove_silence(audio, threshold_db=-40)
        
        # 5. Noise reduction
        audio = await self.reduce_noise(audio)
        
        return ProcessedAudio(
            data=audio,
            sample_rate=16000,
            channels=1,
            duration_ms=len(audio) / 16
        )
```

---

## 10. API Contracts

### 10.1 STT

```yaml
POST /audio/stt
  Request:
    {
      "audio_data": "base64",
      "language": "en",
      "quality_mode": "balanced",  # fast, balanced, accurate
      "options": {
        "punctuate": true,
        "diarize": false,
        "format": "wav"
      }
    }
  Response:
    {
      "transcript": "string",
      "confidence": 0.95,
      "words": [
        { "word": "hello", "start": 0.0, "end": 0.5, "confidence": 0.98 }
      ],
      "language": "en",
      "model_used": "parakeet-tdt",
      "was_upgraded": false,
      "processing_time_ms": 450
    }
```

### 10.2 Meeting Transcript

```yaml
POST /audio/meeting
  Request:
    {
      "audio_data": "base64",
      "min_speakers": 1,
      "max_speakers": 10,
      "identify_speakers": true
    }
  Response:
    {
      "segments": [
        {
          "speaker_id": "SPEAKER_00",
          "start": 0.0,
          "end": 5.2,
          "text": "So let's discuss the roadmap",
          "confidence": 0.93
        },
        {
          "speaker_id": "SPEAKER_01", 
          "start": 5.5,
          "end": 8.1,
          "text": "Great, I have some updates",
          "confidence": 0.91
        }
      ],
      "speaker_count": 2,
      "processing_time_ms": 3200
    }
```

### 10.3 TTS

```yaml
POST /audio/tts
  Request:
    {
      "text": "Hello, your meeting starts in 5 minutes",
      "voice_id": "en-US-AriaNeural",
      "voice_reference": "...",  # Optional for cloning
      "consent_verified": false,
      "speed": 1.0,
      "format": "mp3"
    }
  Response:
    {
      "audio_data": "base64",
      "duration_ms": 2500,
      "format": "mp3"
    }
```

### 10.4 Music ID

```yaml
POST /audio/music/identify
  Request:
    { "audio_data": "base64" }
  Response:
    {
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "score": 0.95,
      "release": "A Night At The Opera"
    }
```

### 10.5 Voice Enrollment

```yaml
POST /audio/enroll
  Request:
    {
      "account_id": "uuid",
      "audio_data": "base64"
    }
  Response:
    {
      "status": "success",
      "message": "Voice enrolled for account ..."
    }
```

---

## 11. Configuration

### 11.1 STT Configuration

```yaml
service:
  name: audio
  port: 8007
  workers: 4

stt:
  # Primary strategy
  default_quality: balanced
  
  # English-first: Parakeet
  primary_model: parakeet-tdt-0.6b-v3
  secondary_model: whisper-large-v3
  
  # Local / low-resource
  local_model: whisper.cpp-base
  
  # Thresholds
  confidence_threshold: 0.85
  upgrade_threshold: 0.75

diarization:
  enabled: true
  min_speakers: 1
  max_speakers: 10
  model: pyannote/heartbeat

speech_understanding:
  enabled: false  # Optional enhancement
  model: iflytek/sensevoice

tts:
  default: coqui-tts
  voice_cloning: xtts-v2
  default_voice: en_US/aristl

music:
  enabled: true
  fingerprint: chromaprint
  service: acoustid
```

---

## 12. Error Codes (RFC 9457)

| Code | Error | HTTP | Cause |
|------|-------|------|-------|
| A001 | invalid-audio-format | 400 | Unsupported codec |
| A002 | audio-too-large | 413 | File exceeds limits |
| A003 | no-speech-detected | 422 | VAD filtered all |
| A004 | stt-timeout | 504 | Processing exceeded |
| A005 | language-unsupported | 400 | Model doesn't support |
| A006 | voice-cloning-denied | 403 | Consent required |

---

## 13. Observability

### 13.1 Key Metrics

| Metric | Type | Alert |
|--------|------|-------|
| stt_latency_p99 | histogram | >2000ms |
| stt_confidence_avg | gauge | <0.85 |
| upgrade_rate | gauge | >0.3 (too many upgrades) |
| diarization_accuracy | gauge | <0.8 |
| tts_latency_p99 | histogram | >3000ms |
| music_id_success_rate | gauge | <0.7 |

---

## 14. Stack Summary

| Layer | Default | Fallback | Trigger |
|-------|---------|---------|---------|
| **STT Fast** | Parakeet LT | Whisper base | quality_mode=fast |
| **STT Accuracy** | Parakeet TDT | Whisper large-v3 | accuracy needed |
| **Diarization** | pyannote | - | meetings option |
| **Speech Understand** | SenseVoice | - | Optional |
| **TTS** | Coqui TTS | XTTS-v2 | Voice cloning |
| **Music** | Chromaprint | - | Explicit |

**Gold rule:** Dual-STT strategy is not optional optimization - it's how you get both latency and quality.

---

*Document owner: Audio Team*  
*Version: 2.0 (STUB)*  
*Last updated: 2026-04-19*