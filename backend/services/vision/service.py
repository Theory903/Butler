from .models import VisionModelProxy
from services.ml.media_processor import MediaProcessor

class VisionService:
    """Stacked vision perception — production implementation routing to GPU nodes."""
    
    def __init__(self, proxy: VisionModelProxy | None = None, processor: MediaProcessor | None = None):
        self.proxy = proxy or VisionModelProxy()
        self._processor = processor or MediaProcessor()
    
    async def detect(self, image_data: bytes, classes: list[str] = None, threshold: float = 0.5) -> dict:
        return await self.proxy.run_yolov8(image_data, threshold)
    
    async def ocr(self, image_data: bytes, languages: list[str] = None) -> dict:
        return await self.proxy.run_paddleocr(image_data, languages or ["en"])
    
    async def reason(self, image_data: bytes, context: dict) -> dict:
        return await self.proxy.run_qwen_vl(image_data, context)
        
    async def segment(self, image_data: bytes, points: list[list[int]]) -> dict:
        return await self.proxy.run_sam2(image_data, points)

    async def process_video(self, video_data: bytes, task: str = "Describe what is happening.") -> dict:
        """Temporal video reasoning via keyframe segmentation."""
        frames = await self._processor.extract_keyframes(video_data)
        if not frames:
            return {"error": "Failed to extract keyframes", "summary": "N/A"}
        
        # Parallel reasoning on frames
        tasks = [self.reason(frame, {"task": task}) for frame in frames]
        frame_results = await asyncio.gather(*tasks)
        
        # Simple temporal aggregation
        summary = " ".join([r.get("reasoning", "") for r in frame_results if r.get("reasoning")])
        
        return {
            "summary": summary,
            "frame_results": frame_results,
            "metadata": {
                "frames_processed": len(frames),
                "model": "qwen2.5-vl-7b-segmented"
            }
        }
