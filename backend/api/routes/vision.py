from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.vision import VisionService


def get_vision() -> VisionService:
    return VisionService()


router = APIRouter(prefix="/vision", tags=["vision"])


class DetectRequest(BaseModel):
    image_data: str  # base64 payload to bypass bytes form upload strictness in mock
    classes: list[str] | None = None
    threshold: float = 0.5


class OCRRequest(BaseModel):
    image_data: str
    languages: list[str] | None = None


class ReasonRequest(BaseModel):
    image_data: str
    context: dict = {}


@router.post("/detect")
async def detect(req: DetectRequest, svc: VisionService = Depends(get_vision)):
    return await svc.detect(req.image_data, req.classes, req.threshold)


@router.post("/ocr")
async def ocr(req: OCRRequest, svc: VisionService = Depends(get_vision)):
    return await svc.ocr(req.image_data, req.languages)


@router.post("/reason")
async def reason(req: ReasonRequest, svc: VisionService = Depends(get_vision)):
    return await svc.reason(req.image_data, req.context)
