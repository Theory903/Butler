import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.deps import get_db
from services.meetings.service import MeetingService

router = APIRouter(prefix="/meetings", tags=["meetings"])


class MeetingCreate(BaseModel):
    title: str
    participants: list[str] = []


class TranscriptionSegment(BaseModel):
    meeting_id: str
    speaker: str
    text: str
    timestamp: float


@router.post("")
async def create_meeting(data: MeetingCreate, service: MeetingService = Depends(get_db)):
    account_id = str(uuid.uuid4())
    return await service.create_meeting(account_id, data.title, data.participants)


@router.post("/transcribe")
async def add_segment(data: TranscriptionSegment, service: MeetingService = Depends(get_db)):
    await service.add_transcription_segment(
        data.meeting_id, data.speaker, data.text, data.timestamp
    )
    return {"status": "success"}


@router.post("/{meeting_id}/finish")
async def finish_meeting(meeting_id: str, service: MeetingService = Depends(get_db)):
    return await service.finish_meeting(meeting_id)


@router.get("")
async def list_meetings(service: MeetingService = Depends(get_db)):
    account_id = str(uuid.uuid4())
    return await service.get_meeting_history(account_id)
