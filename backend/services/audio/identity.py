import logging
import numpy as np
from typing import List, Optional, Dict, Any
from .models import AudioModelProxy, SpeakerSegment
from domain.auth.models import VoiceProfile
from infrastructure.database import async_session_factory
from sqlalchemy import select

logger = logging.getLogger(__name__)

class VoiceIdentityManager:
    """
    Butler Audio Layer 3+: Speaker Identification
    Matches speaker embeddings against enrolled voice profiles.
    """
    
    def __init__(self, proxy: AudioModelProxy, similarity_threshold: float = 0.75):
        self.proxy = proxy
        self.threshold = similarity_threshold
        self._cached_profiles: List[Dict[str, Any]] = []

    async def refresh_profiles(self):
        """Reload voice profiles from database into memory for fast matching."""
        try:
            async with async_session_factory() as db:
                stmt = select(VoiceProfile)
                result = await db.execute(stmt)
                profiles = result.scalars().all()
                self._cached_profiles = [
                    {
                        "account_id": str(p.account_id),
                        "embedding": np.array(p.embedding, dtype=np.float32)
                    }
                    for p in profiles
                ]
            logger.info("voice_profiles_refreshed", count=len(self._cached_profiles))
        except Exception as e:
            logger.error("voice_profiles_refresh_failed", error=str(e))

    async def identify_speaker(self, audio_data: bytes) -> Optional[str]:
        """
        Extracts embedding from audio and matches against known profiles.
        Returns account_id if matched, else None.
        """
        if not self._cached_profiles:
            await self.refresh_profiles()
            
        if not self._cached_profiles:
            return None

        # 1. Extract embedding via Proxy
        try:
            embedding = await self.proxy.extract_embedding(audio_data)
            query_vec = np.array(embedding, dtype=np.float32)
        except Exception as e:
            logger.error("identity_embedding_extraction_failed", error=str(e))
            return None

        # 2. Vector search (Cosine Similarity)
        best_match = None
        max_similarity = -1.0
        
        for profile in self._cached_profiles:
            # Cosine similarity = (A dot B) / (||A|| * ||B||)
            # Assuming embeddings are already normalized by the model
            sim = np.dot(query_vec, profile["embedding"])
            if sim > max_similarity:
                max_similarity = sim
                best_match = profile["account_id"]

        logger.debug("speaker_identification_attempt", similarity=max_similarity, matched=max_similarity > self.threshold)
        
        if max_similarity >= self.threshold:
            return best_match
            
        return None

    async def enroll_voice(self, account_id: str, audio_data: bytes) -> bool:
        """
        Extracts embedding and saves to the user's voice profile.
        """
        try:
            embedding = await self.proxy.extract_embedding(audio_data)
            
            async with async_session_factory() as db:
                # Check if profile exists
                stmt = select(VoiceProfile).where(VoiceProfile.account_id == account_id)
                res = await db.execute(stmt)
                profile = res.scalar_one_or_none()
                
                if profile:
                    profile.embedding = embedding
                else:
                    profile = VoiceProfile(
                        account_id=account_id,
                        embedding=embedding
                    )
                    db.add(profile)
                await db.commit()
            
            await self.refresh_profiles()
            return True
        except Exception as e:
            logger.error("voice_enrollment_failed", account_id=account_id, error=str(e))
            return False
