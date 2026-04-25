"""Communication service - push, email, SMS notifications."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/communication", tags=["communication"])


class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str


class PushRequest(BaseModel):
    user_id: str
    title: str
    body: str
    device_token: str | None = None


class SMSRequest(BaseModel):
    to: str
    body: str


@router.post("/email")
async def send_email(req: EmailRequest):
    return {"sent": True, "to": req.to, "subject": req.subject}


@router.post("/push")
async def send_push(req: PushRequest):
    return {"sent": True, "user_id": req.user_id, "title": req.title}


@router.post("/sms")
async def send_sms(req: SMSRequest):
    return {"sent": True, "to": req.to}


@router.get("/health")
async def health():
    return {"status": "healthy"}
