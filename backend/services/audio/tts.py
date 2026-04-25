import logging

from infrastructure.config import settings

from .models import AudioModelProxy, TTSResult

logger = logging.getLogger(__name__)


class TTSManager:
    """
    Butler Audio: TTS Synthesis Layer
    Handles voice cloning policy and synthesis routing.
    """

    VOICE_CLONING_POLICY = """
    - Voice cloning requires EXPLICIT user consent
    - Usage is logged for audit purposes
    - Users can revoke consent at any time
    """

    def __init__(self, proxy: AudioModelProxy):
        self.proxy = proxy

    async def generate(
        self,
        text: str,
        voice_id: str | None = None,
        voice_reference: bytes | None = None,
        consent_verified: bool = False,
    ) -> TTSResult:
        """
        Generates speech from text.
        Enforces consent policy for cloning.
        """
        # 1. Enforce cloning policy
        if voice_reference and not consent_verified:
            logger.warning("tts_cloning_denied_no_consent", text_length=len(text))
            raise PermissionError("Voice cloning requires EXPLICIT consent (A006)")

        # 2. Choose model and route
        # If voice_reference is present, we use the high-quality cloning model (XTTS-v2) on GPU
        # Otherwise, use standard TTS (Coqui/Piper)
        voice_id = voice_id or settings.TTS_DEFAULT_VOICE

        return await self.proxy.synthesize(text=text, voice_id=voice_id, voice_ref=voice_reference)
