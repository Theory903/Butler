import base64
import logging
import time
from collections.abc import AsyncGenerator

from opentelemetry import trace

from .diarization import SpeakerDiarization
from .errors import InvalidAudioFormatError, NoSpeechDetectedError
from .identity import VoiceIdentityManager
from .models import (
    AudioModelProxy,
    MeetingTranscript,
    MusicMatch,
    StreamUpdate,
    TranscribeResult,
    TTSResult,
)
from .music import MusicIdentifier
from .processors import AudioPreprocessor, VoiceActivityDetector
from .stream_buffer import StreamBuffer
from .stt import DualSTTStrategy
from .tts import TTSManager

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class AudioService:
    """
    Butler Stacked Audio Service Facade.
    Coordinates preprocessing, VAD, STT Strategy, Diarization, Identity, and TTS.
    """

    def __init__(self, buffer: StreamBuffer | None = None):
        self.proxy = AudioModelProxy()
        self.stream_buffer = buffer or StreamBuffer()

        # Layers
        self.preprocessor = AudioPreprocessor()
        self.vad = VoiceActivityDetector()
        self.stt_strategy = DualSTTStrategy(self.proxy)
        self.diarization = SpeakerDiarization()
        self.identity = VoiceIdentityManager(self.proxy)
        self.tts_manager = TTSManager(self.proxy)
        self.music_id = MusicIdentifier()

    async def streaming_transcribe(
        self, chunk_b64: str, language: str | None = None
    ) -> AsyncGenerator[StreamUpdate]:
        """
        Handle real-time audio stream:
        1. Push chunk to buffer
        2. If buffer ready, consume and transcribe
        3. Yield updates
        """
        with tracer.start_as_current_span("audio.stream.segment_processing") as span:
            try:
                chunk = base64.b64decode(chunk_b64)
                await self.stream_buffer.push(chunk)

                # Consume segment (e.g. 1.5s of audio)
                segment = await self.stream_buffer.consume(min_bytes=48000)  # ~1.5s at 16k
                if segment:
                    span.set_attribute("audio.segment.bytes", len(segment))
                    # Preprocess & Detect Speech
                    processed = await self.preprocessor.process(segment)
                    if await self.vad.detect_speech(processed.data):
                        res = await self.stt_strategy.transcribe(
                            processed.data, language=language, quality_mode="fast"
                        )
                        yield StreamUpdate(transcript=res.transcript, is_final=False)
                    else:
                        span.set_attribute("audio.segment.silent", True)

            except Exception as e:
                logger.error("audio_stream_failed", error=str(e))
                span.record_exception(e)
                yield StreamUpdate(transcript="", is_final=True, error=str(e))

    async def transcribe(
        self, audio_data_b64: str, language: str | None = None, quality_mode: str = "balanced"
    ) -> TranscribeResult:
        """
        Stacked STT Workflow:
        1. Base64 Decode
        2. Preprocess (Format → 16kHz → Normalize → Denoise)
        3. VAD (Check for speech)
        4. STT Strategy (Fast/Accurate pass)
        """
        time.perf_counter()

        # 1. Decode
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception:
            raise InvalidAudioFormatError("Invalid base64 audio data")

        # 2. Preprocess
        processed = await self.preprocessor.process(audio_bytes)

        # 3. VAD
        if not await self.vad.detect_speech(processed.data):
            logger.info("audio_rejected_no_speech")
            raise NoSpeechDetectedError

        # 4. STT Strategy
        return await self.stt_strategy.transcribe(
            processed.data, language=language, quality_mode=quality_mode
        )

    async def process_meeting(
        self,
        audio_data_b64: str,
        min_speakers: int = 1,
        max_speakers: int = 10,
        identify_speakers: bool = True,
    ) -> MeetingTranscript:
        """
        Meeting Intelligence Workflow:
        1. Preprocess
        2. Diarize (pyannote)
        3. Identify Speakers (Voice ID)
        4. Transcribe segments (Strategy)
        5. Assemble transcript
        """
        start_ts = time.perf_counter()
        audio_bytes = base64.b64decode(audio_data_b64)
        processed = await self.preprocessor.process(audio_bytes)

        # 1. Diarize
        diarization = await self.diarization.diarize(
            processed.data, min_speakers=min_speakers, max_speakers=max_speakers
        )

        # 2. Identify Speakers (Global pass or per segment)
        # We perform per-segment identification for better accuracy
        final_segments = []
        for segment in diarization.segments:
            # Extract chunk
            chunk = self._extract_chunk(
                processed.data, segment.start, segment.end, processed.sample_rate
            )
            if not chunk:
                continue

            # Identify
            if identify_speakers:
                account_id = await self.identity.identify_speaker(chunk)
                if account_id:
                    segment.speaker_id = f"USER:{account_id}"

            # Transcribe
            res = await self.stt_strategy.transcribe(chunk, quality_mode="fast")
            segment.text = res.transcript
            final_segments.append(segment)

        return MeetingTranscript(
            segments=final_segments,
            speaker_count=diarization.speaker_count,
            processing_time_ms=int((time.perf_counter() - start_ts) * 1000),
        )

    async def enroll_user_voice(self, account_id: str, audio_data_b64: str) -> bool:
        """Register a user's voice for future identification."""
        audio_bytes = base64.b64decode(audio_data_b64)
        processed = await self.preprocessor.process(audio_bytes)
        return await self.identity.enroll_voice(account_id, processed.data)

    def _extract_chunk(self, data: bytes, start: float, end: float, sr: int) -> bytes:
        import numpy as np

        audio_np = np.frombuffer(data, dtype=np.int16)
        start_idx = int(start * sr)
        end_idx = int(end * sr)
        return audio_np[start_idx:end_idx].tobytes()

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        voice_reference_b64: str | None = None,
        consent_verified: bool = False,
    ) -> TTSResult:
        """
        TTS Synthesis with consent check.
        """
        voice_ref = base64.b64decode(voice_reference_b64) if voice_reference_b64 else None
        return await self.tts_manager.generate(
            text=text,
            voice_id=voice_id,
            voice_reference=voice_ref,
            consent_verified=consent_verified,
        )

    async def identify_music(self, audio_data_b64: str) -> MusicMatch:
        """
        Identify music from audio data.
        """
        audio_bytes = base64.b64decode(audio_data_b64)
        return await self.music_id.identify(audio_bytes)

    async def close(self):
        """Cleanup resources"""
        await self.proxy.close()
