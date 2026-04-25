from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import structlog
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_DEFAULT_FFMPEG_TIMEOUT_SEC: Final[float] = 60.0
_DEFAULT_AUDIO_SAMPLE_RATE: Final[int] = 16000
_DEFAULT_MAX_FRAMES: Final[int] = 10
_DEFAULT_FRAME_INTERVAL_SEC: Final[float] = 2.0


@dataclass(frozen=True, slots=True)
class FFmpegRunResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class RawAudioSpec:
    """Optional explicit raw-audio metadata.

    Use this only when the input bytes are truly raw PCM and the caller knows
    the source format. For normal uploaded audio/video files, leave this as None
    and pass containerized bytes such as wav/mp3/m4a/mp4/webm.
    """

    sample_rate: int
    channels: int = 1
    sample_format: str = "s16le"


class MediaProcessor:
    """Hardened media segmentation utility.

    Responsibilities:
    - extract sampled video frames using ffmpeg
    - normalize audio into 16kHz mono WAV PCM
    - bound subprocess runtime and report failures cleanly
    """

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffmpeg_timeout_sec: float = _DEFAULT_FFMPEG_TIMEOUT_SEC,
    ) -> None:
        if ffmpeg_timeout_sec <= 0:
            raise ValueError("ffmpeg_timeout_sec must be greater than 0")

        self.ffmpeg_bin = ffmpeg_bin
        self.ffmpeg_timeout_sec = ffmpeg_timeout_sec

    @tracer.start_as_current_span("media.video.extract_keyframes")
    async def extract_keyframes(
        self,
        video_data: bytes,
        interval_sec: float = _DEFAULT_FRAME_INTERVAL_SEC,
        max_frames: int = _DEFAULT_MAX_FRAMES,
    ) -> list[bytes]:
        """Extract sampled JPEG frames from video bytes.

        Returns a list of JPEG-encoded frame bytes.
        Returns [] on failure.
        """
        if not video_data:
            return []
        if interval_sec <= 0:
            raise ValueError("interval_sec must be greater than 0")
        if max_frames <= 0:
            raise ValueError("max_frames must be greater than 0")

        span = trace.get_current_span()
        span.set_attribute("media.video.interval_sec", interval_sec)
        span.set_attribute("media.video.max_frames", max_frames)

        with tempfile.TemporaryDirectory(prefix="butler-media-video-") as tmpdir:
            workdir = Path(tmpdir)
            input_path = workdir / "input.mp4"
            output_pattern = workdir / "frame_%03d.jpg"

            input_path.write_bytes(video_data)

            cmd = [
                self.ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-vf",
                f"fps=1/{interval_sec}",
                "-frames:v",
                str(max_frames),
                "-q:v",
                "2",
                str(output_pattern),
            ]

            result = await self._run_ffmpeg(cmd)
            if result.timed_out:
                logger.warning(
                    "ffmpeg_extraction_timed_out",
                    timeout_sec=self.ffmpeg_timeout_sec,
                )
                return []

            if result.returncode != 0:
                logger.warning(
                    "ffmpeg_extraction_failed",
                    error=result.stderr.decode("utf-8", errors="ignore"),
                )
                return []

            frames: list[bytes] = []
            for frame_file in sorted(workdir.glob("frame_*.jpg")):
                frames.append(frame_file.read_bytes())

            span.set_attribute("media.video.frames_count", len(frames))
            return frames

    @tracer.start_as_current_span("media.audio.normalize")
    async def normalize_audio(
        self,
        audio_data: bytes,
        sample_rate: int = _DEFAULT_AUDIO_SAMPLE_RATE,
        raw_audio_spec: RawAudioSpec | None = None,
        input_suffix: str = ".bin",
    ) -> bytes:
        """Normalize audio to mono WAV PCM at the requested sample rate.

        Important:
        - For normal file uploads, pass containerized audio bytes and leave
          raw_audio_spec as None.
        - For true raw PCM bytes, supply raw_audio_spec explicitly.
        """
        if not audio_data:
            return b""
        if sample_rate <= 0:
            raise ValueError("sample_rate must be greater than 0")

        span = trace.get_current_span()
        span.set_attribute("media.audio.target_sr", sample_rate)
        span.set_attribute("media.audio.raw_input", raw_audio_spec is not None)

        with tempfile.TemporaryDirectory(prefix="butler-media-audio-") as tmpdir:
            workdir = Path(tmpdir)
            input_path = workdir / f"input{input_suffix}"
            output_path = workdir / "output.wav"

            input_path.write_bytes(audio_data)

            cmd = [
                self.ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
            ]

            if raw_audio_spec is not None:
                if raw_audio_spec.sample_rate <= 0:
                    raise ValueError("raw_audio_spec.sample_rate must be greater than 0")
                if raw_audio_spec.channels <= 0:
                    raise ValueError("raw_audio_spec.channels must be greater than 0")
                cmd.extend(
                    [
                        "-f",
                        raw_audio_spec.sample_format,
                        "-ar",
                        str(raw_audio_spec.sample_rate),
                        "-ac",
                        str(raw_audio_spec.channels),
                    ]
                )

            cmd.extend(
                [
                    "-i",
                    str(input_path),
                    "-ar",
                    str(sample_rate),
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(output_path),
                ]
            )

            result = await self._run_ffmpeg(cmd)
            if result.timed_out:
                logger.warning(
                    "ffmpeg_normalization_timed_out",
                    timeout_sec=self.ffmpeg_timeout_sec,
                )
                return audio_data

            if result.returncode != 0:
                logger.warning(
                    "ffmpeg_normalization_failed",
                    error=result.stderr.decode("utf-8", errors="ignore"),
                )
                return audio_data

            if not output_path.exists():
                logger.warning("ffmpeg_normalization_missing_output")
                return audio_data

            normalized = output_path.read_bytes()
            span.set_attribute("media.audio.output_size_bytes", len(normalized))
            return normalized

    async def _run_ffmpeg(self, cmd: list[str]) -> FFmpegRunResult:
        """Run ffmpeg with bounded execution time and robust cleanup.

        P0 hardening: Use asyncio.create_subprocess_exec with timeout and proper error handling.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.ffmpeg_timeout_sec,
            )
            return FFmpegRunResult(
                returncode=proc.returncode or 0,
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
            )
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return FFmpegRunResult(
                returncode=proc.returncode or -1,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )
        except Exception:
            if proc.returncode is None:
                proc.kill()
                await proc.communicate()
            raise
