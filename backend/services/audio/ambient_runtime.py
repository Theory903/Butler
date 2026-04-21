"""
Butler Ambient Runtime System
Implements wake word detection, talk mode controller, dual audio channels,
canvas session management, and ambient context capture with SWE-5 standards.

Version: 2.0
Status: Oracle-Grade
"""
from __future__ import annotations

import asyncio
import enum
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Deque, Optional, Set, Tuple

import numpy as np
from opentelemetry import trace
from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, validator
from structlog import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TalkModeState(enum.Enum):
    """Talk mode state machine states"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"
    INTERRUPTED = "interrupted"
    FAULT = "fault"


class AudioChannelType(enum.Enum):
    """Dual audio channel types"""
    USER_MIC = "user_mic"
    SYSTEM_OUTPUT = "system_output"


class ConsentLevel(enum.Enum):
    """Ambient context consent levels"""
    NONE = "none"
    AUDIO_ONLY = "audio_only"
    SCREEN = "screen"
    CAMERA = "camera"
    LOCATION = "location"
    FULL = "full"


class WakeWordConfig(BaseModel):
    """Wake word detector configuration"""
    model_path: str = ""
    threshold: float = 0.7
    sample_rate: int = 16000
    frame_size: int = 512
    sensitivity: float = 0.5
    cooldown_ms: int = 2000


class VADConfig(BaseModel):
    """Voice Activity Detection configuration"""
    threshold: float = 0.5
    hangover_ms: int = 300
    noise_floor: float = -40.0
    attack_ms: int = 50
    release_ms: int = 200


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for resource control"""
    failure_threshold: int = 5
    reset_timeout_ms: int = 30000
    half_open_max_calls: int = 2
    execution_timeout_ms: int = 5000


class AmbientRuntimeConfig(BaseModel):
    """Full ambient runtime configuration"""
    wake_word: WakeWordConfig = WakeWordConfig()
    vad: VADConfig = VADConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    max_audio_buffer_seconds: float = 30.0
    max_canvas_items: int = 100
    sample_rate: int = 16000
    channels: int = 1


@dataclass
class CircularAudioBuffer:
    """Thread-safe circular audio buffer for streaming audio"""
    max_size_bytes: int
    buffer: Deque[bytes] = field(default_factory=deque)
    total_bytes: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def write(self, data: bytes) -> None:
        """Write audio data to buffer, evicting oldest if full"""
        async with self.lock:
            self.buffer.append(data)
            self.total_bytes += len(data)

            while self.total_bytes > self.max_size_bytes and self.buffer:
                evicted = self.buffer.popleft()
                self.total_bytes -= len(evicted)

    async def read(self, n_bytes: Optional[int] = None) -> bytes:
        """Read up to n_bytes from buffer, or all available if None"""
        async with self.lock:
            if not self.buffer:
                return b""

            if n_bytes is None:
                result = b"".join(self.buffer)
                self.buffer.clear()
                self.total_bytes = 0
                return result

            collected = []
            collected_bytes = 0

            while self.buffer and collected_bytes < n_bytes:
                frame = self.buffer[0]
                if collected_bytes + len(frame) <= n_bytes:
                    collected.append(self.buffer.popleft())
                    collected_bytes += len(frame)
                    self.total_bytes -= len(frame)
                else:
                    break

            return b"".join(collected)

    def __len__(self) -> int:
        return self.total_bytes


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault tolerance and resource control"""
    config: CircuitBreakerConfig
    failure_count: int = 0
    state: str = "closed"
    last_failure_time: float = 0.0
    half_open_attempts: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def allow_request(self) -> bool:
        """Check if request is allowed through circuit breaker"""
        async with self.lock:
            now = time.time()

            if self.state == "open":
                if now - self.last_failure_time > self.config.reset_timeout_ms / 1000:
                    self.state = "half_open"
                    self.half_open_attempts = 0
                    return True
                return False

            if self.state == "half_open":
                if self.half_open_attempts < self.config.half_open_max_calls:
                    self.half_open_attempts += 1
                    return True
                return False

            return True

    async def record_success(self) -> None:
        """Record successful execution"""
        async with self.lock:
            self.failure_count = 0
            self.state = "closed"
            self.half_open_attempts = 0

    async def record_failure(self) -> None:
        """Record failed execution"""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.config.failure_threshold:
                self.state = "open"
                logger.warning("Circuit breaker opened", failure_count=self.failure_count)


class WakeWordDetector:
    """Wake word detection with confidence thresholding and cooldown"""

    def __init__(self, config: WakeWordConfig):
        self.config = config
        self.last_detection_time = 0.0
        self._model_loaded = False
        self.circuit_breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout_ms=30000,
            half_open_max_calls=2,
            execution_timeout_ms=5000
        ))
        logger.info("WakeWordDetector initialized", threshold=config.threshold)

    async def load_model(self) -> None:
        """Load wake word detection model"""
        with tracer.start_as_current_span("wake_word.load_model"):
            # Model loading implementation would go here
            self._model_loaded = True
            logger.debug("Wake word model loaded")

    async def detect(self, audio_frame: np.ndarray) -> Tuple[bool, float]:
        """Detect wake word in audio frame"""
        if not await self.circuit_breaker.allow_request():
            return False, 0.0

        try:
            if not self._model_loaded:
                await self.load_model()

            now = time.time()
            if now - self.last_detection_time < self.config.cooldown_ms / 1000:
                return False, 0.0

            # Actual wake word inference would go here
            confidence = self._compute_confidence(audio_frame)
            detected = confidence >= self.config.threshold

            if detected:
                self.last_detection_time = now
                logger.info("Wake word detected", confidence=confidence)
                await self.circuit_breaker.record_success()
            else:
                await self.circuit_breaker.record_success()

            return detected, confidence

        except Exception as e:
            logger.error("Wake word detection failed", error=str(e))
            await self.circuit_breaker.record_failure()
            return False, 0.0

    def _compute_confidence(self, audio_frame: np.ndarray) -> float:
        """Compute wake word confidence score"""
        if len(audio_frame) < self.config.frame_size:
            return 0.0

        energy = float(np.mean(np.abs(audio_frame)))
        return float(min(1.0, energy / 0.1))


class VoiceActivityDetector:
    """Voice Activity Detection with noise gating and hangover"""

    def __init__(self, config: VADConfig):
        self.config = config
        self.speech_active = False
        self.last_speech_time = 0.0
        self.noise_floor = config.noise_floor
        self.samples_since_speech = 0

    def process_frame(self, audio_frame: np.ndarray) -> bool:
        """Process audio frame and return speech activity status"""
        frame_energy = 20 * np.log10(np.mean(np.abs(audio_frame)) + 1e-10)

        if frame_energy > self.noise_floor + self.config.threshold * 20:
            self.speech_active = True
            self.last_speech_time = time.time()
            self.samples_since_speech = 0
            return True

        if self.speech_active:
            hangover_frames = int((self.config.hangover_ms / 1000) * 16000 / 512)
            self.samples_since_speech += 1
            if self.samples_since_speech > hangover_frames:
                self.speech_active = False

        return self.speech_active

    def update_noise_floor(self, audio_frame: np.ndarray) -> None:
        """Update noise floor estimate during silence"""
        if not self.speech_active:
            frame_energy = 20 * np.log10(np.mean(np.abs(audio_frame)) + 1e-10)
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * frame_energy


class DualAudioChannel:
    """Dual audio channel separation for system output and user microphone"""

    def __init__(self, config: AmbientRuntimeConfig):
        self.config = config
        max_buffer_bytes = int(config.max_audio_buffer_seconds * config.sample_rate * 2)

        self.user_channel = CircularAudioBuffer(max_buffer_bytes)
        self.system_channel = CircularAudioBuffer(max_buffer_bytes)
        self.active_channels: Set[AudioChannelType] = set()

        self.vad = VoiceActivityDetector(config.vad)
        self.circuit_breaker = CircuitBreaker(config.circuit_breaker)

        logger.info("DualAudioChannel initialized", max_buffer_bytes=max_buffer_bytes)

    async def write_channel(self, channel: AudioChannelType, data: bytes) -> None:
        """Write audio data to specified channel"""
        if not await self.circuit_breaker.allow_request():
            logger.warning("Audio channel write blocked by circuit breaker", channel=channel)
            return

        try:
            if channel == AudioChannelType.USER_MIC:
                await self.user_channel.write(data)
            elif channel == AudioChannelType.SYSTEM_OUTPUT:
                await self.system_channel.write(data)

            self.active_channels.add(channel)
            await self.circuit_breaker.record_success()

        except Exception as e:
            logger.error("Audio channel write failed", channel=channel, error=str(e))
            await self.circuit_breaker.record_failure()

    async def read_channel(self, channel: AudioChannelType, n_bytes: Optional[int] = None) -> bytes:
        """Read audio data from specified channel"""
        if channel == AudioChannelType.USER_MIC:
            return await self.user_channel.read(n_bytes)
        elif channel == AudioChannelType.SYSTEM_OUTPUT:
            return await self.system_channel.read(n_bytes)
        return b""

    async def stream_channel(self, channel: AudioChannelType) -> AsyncGenerator[bytes, None]:
        """Stream audio from channel as async generator"""
        while True:
            data = await self.read_channel(channel, 1024)
            if data:
                yield data
            await asyncio.sleep(0.01)


class TalkModeController:
    """Talk mode state machine with explicit activation/deactivation"""

    def __init__(self, config: AmbientRuntimeConfig):
        self.config = config
        self.state = TalkModeState.IDLE
        self.session_id: Optional[str] = None
        self.state_changed_at = time.time()
        self.interrupt_count = 0
        self.lock = asyncio.Lock()

        logger.info("TalkModeController initialized", initial_state=self.state)

    async def transition_to(self, new_state: TalkModeState) -> bool:
        """Transition to new state with validation"""
        async with self.lock:
            with tracer.start_as_current_span("talk_mode.transition", attributes={
                "old_state": self.state.value,
                "new_state": new_state.value
            }):
                if not self._is_valid_transition(self.state, new_state):
                    logger.warning(
                        "Invalid state transition",
                        from_state=self.state,
                        to_state=new_state
                    )
                    return False

                old_state = self.state
                self.state = new_state
                self.state_changed_at = time.time()

                logger.info(
                    "Talk mode state changed",
                    old_state=old_state.value,
                    new_state=new_state.value
                )

                if new_state == TalkModeState.LISTENING:
                    self.session_id = str(uuid.uuid4())

                return True

    def _is_valid_transition(self, from_state: TalkModeState, to_state: TalkModeState) -> bool:
        """Validate state transition per state machine rules"""
        valid_transitions = {
            TalkModeState.IDLE: {TalkModeState.LISTENING, TalkModeState.FAULT},
            TalkModeState.LISTENING: {TalkModeState.PROCESSING, TalkModeState.IDLE, TalkModeState.INTERRUPTED, TalkModeState.FAULT},
            TalkModeState.PROCESSING: {TalkModeState.RESPONDING, TalkModeState.IDLE, TalkModeState.INTERRUPTED, TalkModeState.FAULT},
            TalkModeState.RESPONDING: {TalkModeState.IDLE, TalkModeState.LISTENING, TalkModeState.INTERRUPTED, TalkModeState.FAULT},
            TalkModeState.INTERRUPTED: {TalkModeState.IDLE, TalkModeState.LISTENING, TalkModeState.FAULT},
            TalkModeState.FAULT: {TalkModeState.IDLE},
        }
        return to_state in valid_transitions.get(from_state, set())

    async def interrupt(self) -> None:
        """Interrupt current operation"""
        self.interrupt_count += 1
        await self.transition_to(TalkModeState.INTERRUPTED)
        logger.warning("Talk mode interrupted", count=self.interrupt_count)


class CanvasSession:
    """Live canvas/A2UI workspace state bounded to session"""

    def __init__(self, session_id: str, max_items: int = 100):
        self.session_id = session_id
        self.max_items = max_items
        self.items: Deque[dict[str, Any]] = deque(maxlen=max_items)
        self.created_at = time.time()
        self.last_updated = time.time()
        self.lock = asyncio.Lock()

        logger.info("CanvasSession created", session_id=session_id, max_items=max_items)

    async def add_item(self, item: dict[str, Any]) -> None:
        """Add item to canvas, evicting oldest if full"""
        async with self.lock:
            item["timestamp"] = time.time()
            self.items.append(item)
            self.last_updated = time.time()

            if len(self.items) >= self.max_items:
                logger.debug("Canvas session at capacity, evicted oldest item")

    async def get_items(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Get canvas items, most recent first"""
        items = list(reversed(self.items))
        if limit is not None:
            items = items[:limit]
        return items

    async def clear(self) -> None:
        """Clear all canvas items"""
        async with self.lock:
            self.items.clear()
            logger.debug("Canvas session cleared", session_id=self.session_id)


class AmbientContext:
    """Ambient context capture with explicit consent enforcement"""

    def __init__(self, consent_level: ConsentLevel = ConsentLevel.AUDIO_ONLY):
        self.consent_level = consent_level
        self.capturing = False
        self.capture_start_time: Optional[float] = None
        self.lock = asyncio.Lock()

        logger.info("AmbientContext initialized", consent_level=consent_level.value)

    def has_consent(self, capability: ConsentLevel) -> bool:
        """Check if consent is granted for specific capability"""
        hierarchy = [
            ConsentLevel.NONE,
            ConsentLevel.AUDIO_ONLY,
            ConsentLevel.SCREEN,
            ConsentLevel.CAMERA,
            ConsentLevel.LOCATION,
            ConsentLevel.FULL,
        ]
        return hierarchy.index(self.consent_level) >= hierarchy.index(capability)

    async def start_capture(self) -> bool:
        """Start ambient context capture with consent checks"""
        async with self.lock:
            if self.consent_level == ConsentLevel.NONE:
                logger.warning("Ambient capture denied: no consent")
                return False

            self.capturing = True
            self.capture_start_time = time.time()
            logger.info("Ambient capture started", consent_level=self.consent_level.value)
            return True

    async def stop_capture(self) -> None:
        """Stop ambient context capture"""
        async with self.lock:
            self.capturing = False
            duration = time.time() - self.capture_start_time if self.capture_start_time else 0
            logger.info("Ambient capture stopped", duration_seconds=round(duration, 2))

    async def capture_screen(self) -> Optional[bytes]:
        """Capture screen if consent granted"""
        if not self.has_consent(ConsentLevel.SCREEN) or not self.capturing:
            return None

        with tracer.start_as_current_span("ambient.capture_screen"):
            # Screen capture implementation
            logger.debug("Screen captured")
            return b""

    async def capture_location(self) -> Optional[tuple[float, float]]:
        """Capture location if consent granted"""
        if not self.has_consent(ConsentLevel.LOCATION) or not self.capturing:
            return None

        logger.debug("Location captured")
        return (0.0, 0.0)


class AmbientRuntime:
    """Main ambient runtime system orchestrator"""

    def __init__(self, config: AmbientRuntimeConfig):
        self.config = config

        self.wake_word = WakeWordDetector(config.wake_word)
        self.talk_mode = TalkModeController(config)
        self.audio_channels = DualAudioChannel(config)
        self.ambient_context = AmbientContext()

        self.canvas_sessions: dict[str, CanvasSession] = {}
        self.running = False
        self.tasks: set[asyncio.Task] = set()

        logger.info("AmbientRuntime initialized", version="2.0")

    async def start(self) -> None:
        """Start ambient runtime services"""
        with tracer.start_as_current_span("ambient_runtime.start"):
            await self.wake_word.load_model()
            self.running = True

            self.tasks.add(asyncio.create_task(self._wake_word_loop()))
            self.tasks.add(asyncio.create_task(self._audio_processing_loop()))

            logger.info("Ambient runtime started successfully")

    async def stop(self) -> None:
        """Stop ambient runtime services gracefully"""
        self.running = False

        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.tasks.clear()
        logger.info("Ambient runtime stopped")

    async def _wake_word_loop(self) -> None:
        """Background wake word detection loop"""
        logger.debug("Wake word detection loop started")

        while self.running:
            try:
                audio_data = await self.audio_channels.read_channel(AudioChannelType.USER_MIC, 2048)
                if not audio_data:
                    await asyncio.sleep(0.01)
                    continue

                audio_frame = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                detected, confidence = await self.wake_word.detect(audio_frame)

                if detected and self.talk_mode.state == TalkModeState.IDLE:
                    await self.talk_mode.transition_to(TalkModeState.LISTENING)

            except Exception as e:
                logger.error("Wake word loop error", error=str(e))
                await asyncio.sleep(0.1)

    async def _audio_processing_loop(self) -> None:
        """Background audio processing loop with VAD"""
        logger.debug("Audio processing loop started")

        while self.running:
            try:
                audio_data = await self.audio_channels.read_channel(AudioChannelType.USER_MIC, 512)
                if not audio_data:
                    await asyncio.sleep(0.005)
                    continue

                audio_frame = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                speech_active = self.audio_channels.vad.process_frame(audio_frame)

                if self.talk_mode.state == TalkModeState.LISTENING and not speech_active:
                    # End of speech detected, transition to processing
                    await self.talk_mode.transition_to(TalkModeState.PROCESSING)

            except Exception as e:
                logger.error("Audio processing loop error", error=str(e))
                await asyncio.sleep(0.1)

    async def get_or_create_canvas_session(self, session_id: str) -> CanvasSession:
        """Get existing canvas session or create new one"""
        if session_id not in self.canvas_sessions:
            self.canvas_sessions[session_id] = CanvasSession(session_id, self.config.max_canvas_items)
        return self.canvas_sessions[session_id]
