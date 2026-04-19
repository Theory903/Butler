import logging
import asyncio
from typing import List, Dict, Optional
from .models import DiarizationResult, SpeakerSegment
from infrastructure.config import settings

logger = logging.getLogger(__name__)

class SpeakerDiarization:
    """
    Butler Audio Layer 3: Speaker Diarization
    Identifies 'who is speaking when'.
    Uses pyannote.audio for segmentation.
    """
    
    def __init__(self, hf_token: Optional[str] = None):
        self.hf_token = hf_token or settings.HUGGINGFACE_TOKEN
        self._pipeline = None

    def _ensure_pipeline(self):
        """
        Production initialization of pyannote speaker-diarization pipeline.
        Requires HUGGINGFACE_TOKEN and gated-model access.
        """
        if self._pipeline is None:
            if not self.hf_token:
                logger.warning("diarization_hf_token_missing - Check .env for HUGGINGFACE_TOKEN")
                return None
            
            try:
                from pyannote.audio import Pipeline
                self._pipeline = Pipeline.from_pretrained(
                    settings.DIARIZATION_MODEL,
                    use_auth_token=self.hf_token
                )
                # Move to GPU if available
                import torch
                if torch.cuda.is_available():
                    self._pipeline.to(torch.device("cuda"))
            except Exception as e:
                logger.error("diarization_pipeline_init_failed", error=str(e))
                return None
        return self._pipeline

    async def diarize(
        self, 
        audio_data: bytes, 
        min_speakers: int = 1, 
        max_speakers: int = 10
    ) -> DiarizationResult:
        """
        Processes audio data to extract speaker segments.
        Offloads the heavy model inference to a thread pool.
        """
        pipeline = self._ensure_pipeline()
        
        if pipeline is None:
            logger.warning("diarization_falling_back_to_mock")
            return DiarizationResult(
                segments=[SpeakerSegment(speaker_id="SPEAKER_00", start=0.0, end=1.0, confidence=1.0)],
                speaker_count=1,
                segments_by_speaker={"SPEAKER_00": []}
            )

        try:
            # pyannote expects a file path or a dict with "content" in bytes
            # For bytes, we need to wrap it appropriately
            audio_io = {"content": audio_data}
            
            loop = asyncio.get_running_loop()
            diarization = await loop.run_in_executor(
                None,
                lambda: pipeline(audio_io, min_speakers=min_speakers, max_speakers=max_speakers)
            )
            
            segments = []
            segments_by_speaker = {}
            
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                seg = SpeakerSegment(
                    speaker_id=speaker,
                    start=turn.start,
                    end=turn.end,
                    confidence=1.0 # pyannote internal confidence not always easily exposed here
                )
                segments.append(seg)
                if speaker not in segments_by_speaker:
                    segments_by_speaker[speaker] = []
                segments_by_speaker[speaker].append(seg)
                
            return DiarizationResult(
                segments=segments,
                speaker_count=len(segments_by_speaker),
                segments_by_speaker=segments_by_speaker
            )
            
        except Exception as e:
            logger.error("diarization_failed", error=str(e))
            raise
class SpeakerDiarization:
    """
    Butler Audio Layer 3: Speaker Diarization
    Identifies 'who is speaking when'.
    Uses pyannote.audio for segmentation.
    """
    
    def __init__(self, hf_token: Optional[str] = None):
        self.hf_token = hf_token or settings.HUGGINGFACE_TOKEN
        self._pipeline = None

    def _ensure_pipeline(self):
        """
        Production initialization of pyannote speaker-diarization pipeline.
        Requires HUGGINGFACE_TOKEN and gated-model access.
        """
        if self._pipeline is None:
            if not self.hf_token:
                logger.warning("diarization_hf_token_missing - Check .env for HUGGINGFACE_TOKEN")
                return None
            
            try:
                from pyannote.audio import Pipeline
                self._pipeline = Pipeline.from_pretrained(
                    settings.DIARIZATION_MODEL,
                    use_auth_token=self.hf_token
                )
                # Move to GPU if available
                import torch
                if torch.cuda.is_available():
                    self._pipeline.to(torch.device("cuda"))
            except Exception as e:
                logger.error("diarization_pipeline_init_failed", error=str(e))
                return None
        return self._pipeline

    async def diarize(
        self, 
        audio_data: bytes, 
        min_speakers: int = 1, 
        max_speakers: int = 10
    ) -> DiarizationResult:
        """
        Processes audio data to extract speaker segments.
        Offloads the heavy model inference to a thread pool.
        """
        pipeline = self._ensure_pipeline()
        
        if pipeline is None:
            logger.warning("diarization_falling_back_to_mock")
            return DiarizationResult(
                segments=[SpeakerSegment(speaker_id="SPEAKER_00", start=0.0, end=1.0, confidence=1.0)],
                speaker_count=1,
                segments_by_speaker={"SPEAKER_00": []}
            )

        try:
            # pyannote expects a file path or a dict with "content" in bytes
            audio_io = {"content": audio_data}
            
            loop = asyncio.get_running_loop()
            diarization = await loop.run_in_executor(
                None,
                lambda: pipeline(audio_io, min_speakers=min_speakers, max_speakers=max_speakers)
            )
            
            segments = []
            segments_by_speaker = {}
            
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                seg = SpeakerSegment(
                    speaker_id=speaker,
                    start=turn.start,
                    end=turn.end,
                    confidence=1.0 
                )
                segments.append(seg)
                if speaker not in segments_by_speaker:
                    segments_by_speaker[speaker] = []
                segments_by_speaker[speaker].append(seg)
                
            return DiarizationResult(
                segments=segments,
                speaker_count=len(segments_by_speaker),
                segments_by_speaker=segments_by_speaker
            )
            
        except Exception as e:
            logger.error("diarization_failed", error=str(e))
            raise
