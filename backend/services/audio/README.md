# Butler Audio Service

This package implements the **Stacked Audio System (v3.2)** for Butler. It provides a robust, multi-layered pipeline for processing streaming and static audio through speech detection, multi-pass transcription, speaker diarization, and voice identification.

> **Full Technical Spec:** [`../../../docs/02-services/audio.md`](../../../docs/02-services/audio.md)

## 🏗 Architecture & Modules

The Audio service never executes "dumb" monolithic transcriptions. It breaks perception into optimized layers:

*   **`service.py`**: The `AudioService` facade. Coordinates all audio logic (Preprocess -> VAD -> Diarization -> Voice ID -> Dual STT).
*   **`models.py`**: Defines the `AudioModelProxy`, a robust `httpx` client routing complex tasks (like embeddings or Whisper large-v3) to our external GPU-inference clusters. It seamlessly falls back to mocks in development.
*   **`processors.py`**: Handles Layer 1 Preprocessing. Leverages `ffmpeg` for resampling/normalizing, `noisereduce` for denoising, and a native `onnxruntime` runner executing the **Silero VAD** model for near-zero-latency Voice Activity Detection.
*   **`stt.py`**: Implements the **Dual-STT Strategy**. It conducts a fast local pass (e.g., small whisper/parakeet) and analyzes confidence thresholds. If confidence is low, it dynamically upgrades to an accurate pass (`large-v3`) ensuring latency and accuracy are explicitly balanced.
*   **`diarization.py`**: The `SpeakerDiarization` module uses `pyannote.audio` clusters to understand exactly *who* spoke *when* during a meeting or multi-caller stream.
*   **`identity.py`**: Contains `VoiceIdentityManager`, matching GPU-extracted embeddings against a user's verified `VoiceProfile` to identify speakers in a stream using cosine similarity.
*   **`tts.py` & `music.py`**: Voice synthesis and Shazam-style music detection pipelines.

## ✨ Key Features
1.  **VAD Pipeline:** Rejects non-speech streams or silent connections early via ONNX models, saving massive GPU compute.
2.  **Meeting Intelligence:** The `process_meeting()` workflow diarizes the audio track first, extracts the voice embeddings per-segment to identify known users, and correctly formats transcripts as a multi-party conversation.
3.  **Dual-Pass Pipeline:** You can switch dynamically between 'fast', 'balanced', and 'accurate' quality modes depending on UI application real-time needs.

## 🛠 Required Environment
*   **FFmpeg CLI** installed on the host machine.
*   `silero_vad.onnx` weights located in `BUTLER_DATA_DIR/models/`.
*   Python Deps: `httpx`, `soundfile`, `ffmpeg-python`, `noisereduce`, `onnxruntime`, `pyacoustid`.

## 🧪 Common Operations

**Full Processing Workflow**
```python
# Fully understand a meeting recording
transcript = await audio_service.process_meeting(
    audio_base64, 
    min_speakers=2, 
    identify_speakers=True
)

for segment in transcript.segments:
    # E.g., "[USER:2bf...] 0:13 - 0:15: That sounds like a plan."
    print(f"[{segment.speaker_id}] {segment.start} - {segment.end}: {segment.text}")
```
