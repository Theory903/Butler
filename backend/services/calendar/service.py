import structlog
from datetime import datetime, UTC, timedelta
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logger = structlog.get_logger(__name__)

class GoogleCalendarService:
    """Butler Internal Google Calendar Service."""
    
    def __init__(self, credentials_dict: Optional[Dict[str, Any]] = None):
        self._credentials = None
        if credentials_dict:
            self._credentials = Credentials.from_authorized_user_info(credentials_dict)

    def _get_service(self):
        if not self._credentials:
            raise ValueError("Google Calendar credentials not provided.")
        return build("calendar", "v3", credentials=self._credentials)

    async def get_upcoming_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch list of upcoming calendar items."""
        try:
            service = self._get_service()
            time_min = datetime.now(UTC).isoformat()
            time_max = (datetime.now(UTC) + timedelta(days=days)).isoformat()
            
            events_result = service.events().list(
                calendarId='primary', 
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            return [
                {
                    "id": event.get("id"),
                    "title": event.get("summary"),
                    "description": event.get("description"),
                    "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
                    "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
                    "location": event.get("location"),
                    "attendees": [a.get("email") for a in event.get("attendees", [])]
                }
                for event in events
            ]
        except Exception as exc:
            logger.error("calendar_fetch_failed", error=str(exc))
            return []

    async def create_event(self, title: str, start_time: str, duration_minutes: int, attendees: List[str] = []) -> Dict[str, Any]:
        """Book a new calendar event."""
        try:
            service = self._get_service()
            
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            event_body = {
                'summary': title,
                'start': {'dateTime': start_dt.isoformat()},
                'end': {'dateTime': end_dt.isoformat()},
                'attendees': [{'email': email} for email in attendees]
            }
            
            event = service.events().insert(calendarId='primary', body=event_body).execute()
            
            logger.info("calendar_event_created", event_id=event.get("id"), title=title)
            return {
                "status": "success",
                "event_id": event.get("id"),
                "html_link": event.get("htmlLink")
            }
        except Exception as exc:
            logger.error("calendar_create_failed", error=str(exc))
            return {"status": "error", "message": str(exc)}
