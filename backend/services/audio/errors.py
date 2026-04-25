from core.errors import Problem


class AudioError(Problem):
    """Base class for all Audio service problems."""


class InvalidAudioFormatError(AudioError):
    def __init__(self, detail: str = "Unsupported audio codec or format."):
        super().__init__(
            type="audio/invalid-audio-format",
            title="Invalid Audio Format",
            status=400,
            detail=detail,
            code="A001",
        )


class AudioTooLargeError(AudioError):
    def __init__(self, detail: str = "Audio file exceeds internal size limits."):
        super().__init__(
            type="audio/audio-too-large",
            title="Audio Too Large",
            status=413,
            detail=detail,
            code="A002",
        )


class NoSpeechDetectedError(AudioError):
    def __init__(self, detail: str = "VAD filtered all content; no speech detected."):
        super().__init__(
            type="audio/no-speech-detected",
            title="No Speech Detected",
            status=422,
            detail=detail,
            code="A003",
        )


class STTTimeoutError(AudioError):
    def __init__(self, detail: str = "Transcription processing exceeded allowed timeout."):
        super().__init__(
            type="audio/stt-timeout", title="STT Timeout", status=504, detail=detail, code="A004"
        )


class LanguageUnsupportedError(AudioError):
    def __init__(self, language: str):
        super().__init__(
            type="audio/language-unsupported",
            title="Language Unsupported",
            status=400,
            detail=f"The requested language '{language}' is not supported by the current models.",
            code="A005",
        )


class VoiceCloningDeniedError(AudioError):
    def __init__(self, detail: str = "Voice cloning requires EXPLICIT user consent."):
        super().__init__(
            type="audio/voice-cloning-denied",
            title="Voice Cloning Denied",
            status=403,
            detail=detail,
            code="A006",
        )
