import logging
import time
import asyncio
from typing import Optional
from .models import AudioModelProxy, TranscribeResult, WordInfo
from infrastructure.config import settings

logger = logging.getLogger(__name__)

class DualSTTStrategy:
    """
    Butler Audio Layer 2: STT Strategy
    Orchestrates Dual-STT: Fast Pass → Accuracy Pass if confidence is low.
    """
    
    def __init__(self, proxy: AudioModelProxy):
        self.proxy = proxy

    async def transcribe(
        self, 
        audio_data: bytes,
        language: Optional[str] = None,
        quality_mode: str = "balanced"  # fast, balanced, accurate
    ) -> TranscribeResult:
        """
        Main entry point for transcription with strategy routing.
        """
        quality_mode = quality_mode or settings.STT_DEFAULT_QUALITY
        
        # 1. Choose Strategy
        if quality_mode == "fast":
            return await self.fast_pass(audio_data, language)
        
        elif quality_mode == "balanced":
            # Start with fast pass
            result = await self.fast_pass(audio_data, language)
            
            # If confidence is below threshold, upgrade to accurate pass
            if result.confidence < settings.STT_CONFIDENCE_THRESHOLD:
                logger.info("stt_quality_upgrade_triggered", confidence=result.confidence)
                accurate_result = await self.accurate_pass(audio_data, language)
                accurate_result.was_upgraded = True
                return accurate_result
            
            return result
        
        else: # accurate
            return await self.accurate_pass(audio_data, language)

    async def fast_pass(self, audio_data: bytes, language: Optional[str]) -> TranscribeResult:
        """
        Fast pass using Parakeet-LT (English) or Whisper-Base (Multilingual).
        In a production environment, this might run locally on CPU or on a fast GPU slice.
        """
        start = time.perf_counter()
        model = settings.STT_LOCAL_MODEL if language != "en" else "parakeet-lt"
        
        # For now, we route both to the proxy with model hints
        result = await self.proxy.transcribe(audio_data, language=language, model=model)
        
        # Adjust processing time to reflect total strategy time if needed
        result.processing_time_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def accurate_pass(self, audio_data: bytes, language: Optional[str]) -> TranscribeResult:
        """
        Accurate pass using Parakeet-TDT (English) or Whisper-Large-V3 (Multilingual).
        Always routes to the high-performance GPU worker.
        """
        start = time.perf_counter()
        model = settings.STT_SECONDARY_MODEL if language != "en" else settings.STT_PRIMARY_MODEL
        
        result = await self.proxy.transcribe(audio_data, language=language, model=model)
        
        result.processing_time_ms = int((time.perf_counter() - start) * 1000)
        return result
