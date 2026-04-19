from .models import VisionModelProxy

class VisionService:
    """Stacked vision perception — production implementation routing to GPU nodes."""
    
    def __init__(self, proxy: VisionModelProxy | None = None):
        self.proxy = proxy or VisionModelProxy()
    
    async def detect(self, image_data: bytes, classes: list[str] = None, threshold: float = 0.5) -> dict:
        return await self.proxy.run_yolov8(image_data, threshold)
    
    async def ocr(self, image_data: bytes, languages: list[str] = None) -> dict:
        return await self.proxy.run_paddleocr(image_data, languages or ["en"])
    
    async def reason(self, image_data: bytes, context: dict) -> dict:
        return await self.proxy.run_qwen_vl(image_data, context)
        
    async def segment(self, image_data: bytes, points: list[list[int]]) -> dict:
        return await self.proxy.run_sam2(image_data, points)
