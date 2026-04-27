import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import ffmpeg
import noisereduce as nr
import numpy as np
import onnxruntime as ort

from infrastructure.config import settings

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProcessedAudio:
    data: bytes
    sample_rate: int
    channels: int
    duration_ms: int


class AudioPreprocessor:
    """
    Butler Audio Layer 1: Preprocessing
    Handles format conversion, resampling, normalization, and noise reduction.
    """

    def __init__(self, target_sample_rate: int = 16000):
        self.target_sample_rate = target_sample_rate

    async def process(self, audio_bytes: bytes) -> ProcessedAudio:
        """
        Execute the preprocessing pipeline.
        """
        try:
            # 1. Format conversion & Resampling via FFmpeg
            out, err = (
                ffmpeg.input("pipe:0")
                .output(
                    "pipe:1",
                    format="f32le",
                    acodec="pcm_f32le",
                    ac=1,
                    ar=str(self.target_sample_rate),
                )
                .run(input=audio_bytes, capture_stdout=True, capture_stderr=True)
            )
            audio_np = np.frombuffer(out, dtype=np.float32)
        except ffmpeg.Error as e:
            logger.error(
                "audio_preprocessing_ffmpeg_failed", error=e.stderr.decode() if e.stderr else str(e)
            )
            raise ValueError("Invalid audio format or ffmpeg processing failed")

        if len(audio_np) == 0:
            raise ValueError("Audio processing resulted in zero length buffer")

        # 2. Volume Normalization
        max_val = np.max(np.abs(audio_np))
        if max_val > 0:
            audio_np = audio_np / max_val

        # 3. Noise Reduction (Offloaded to thread pool)
        loop = asyncio.get_running_loop()
        audio_denoised = await loop.run_in_executor(
            None, lambda: nr.reduce_noise(y=audio_np, sr=self.target_sample_rate, stationary=False)
        )

        # Convert back to 16-bit PCM
        audio_int16 = (audio_denoised * 32767).astype(np.int16)
        output_bytes = audio_int16.tobytes()

        return ProcessedAudio(
            data=output_bytes,
            sample_rate=self.target_sample_rate,
            channels=1,
            duration_ms=int(len(audio_int16) / (self.target_sample_rate / 1000)),
        )


class VoiceActivityDetector:
    """
    Butler Audio Layer 1: Production VAD
    Uses Silero VAD (ONNX) for accurate human speech detection.
    """

    def __init__(self, model_path: str | None = None):
        # Default to a models directory in the butler data root
        self.model_path = model_path or str(
            Path(settings.BUTLER_DATA_DIR) / "models/silero_vad.onnx"
        )
        self._session = None
        self._state = np.zeros((2, 1, 64), dtype=np.float32)  # Silero VAD state
        self._sr = np.array([16000], dtype=np.int64)

    def _ensure_session(self):
        """Lazy load the ONNX session"""
        if self._session is None:
            if not os.path.exists(self.model_path):
                logger.warning(
                    f"VAD model not found at {self.model_path}. Falling back to energy detection."
                )
                return None
            try:
                self._session = ort.InferenceSession(self.model_path)
            except Exception as e:
                logger.error("vad_session_init_failed", error=str(e))
                return None
        return self._session

    async def detect_speech(self, audio_bytes: bytes, threshold: float = 0.5) -> bool:
        """
        Detects if speech is present in the chunk using Silero VAD.
        """
        session = self._ensure_session()
        if not session:
            # Fallback to simple energy-based VAD implemented earlier
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(audio_np**2))
            return rms > 0.01

        # Process via ONNX (Offloaded to thread pool)
        # Silero VAD expects [batch, samples]
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio_np) < 512:  # Min chunk size for Silero
            return False

        input_tensor = audio_np[np.newaxis, :]

        loop = asyncio.get_running_loop()
        outputs = await loop.run_in_executor(
            None,
            lambda: session.run(
                None, {"input": input_tensor, "sr": self._sr, "state": self._state}
            ),
        )

        prob, self._state = outputs
        return prob > threshold

    def reset(self):
        """Reset VAD state between sessions"""
        self._state = np.zeros((2, 1, 64), dtype=np.float32)
