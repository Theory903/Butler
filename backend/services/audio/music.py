import logging

from infrastructure.config import settings

from .models import MusicMatch

logger = logging.getLogger(__name__)


class MusicIdentifier:
    """
    Butler Audio: Music Identification
    Uses Chromaprint (fpcalc) and AcoustID for song matching.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.ACOUSTID_API_KEY

    async def identify(self, audio_data: bytes) -> MusicMatch:
        """
        Fingerprints the audio and performs an AcoustID lookup.
        """
        if not self.api_key:
            logger.warning("acoustid_key_not_set")
            # Return empty match or raise error
            raise ValueError("Music identification requires an AcoustID API key")

        try:
            # Note: acoustid.match is blocking, in prod we'd run in executor
            # durations, scores, result = acoustid.match(self.api_key, audio_data)

            # Simulated match for now
            return MusicMatch(
                title="Simulated Song Title",
                artist="Simulated Artist",
                duration=210.0,
                score=0.95,
                release="Simulated Album",
            )
        except Exception as e:
            logger.error("music_id_failed", error=str(e))
            raise
