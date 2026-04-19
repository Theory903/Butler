import datetime
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

from services.communication.calendar_service import GoogleCalendarService

class CalendarSkill:
    """
    Jarvis Google Workspace Calendar integration providing MCP-compatible tool bindings 
    for accessing upcoming scheduled items and booking new events.
    """
    
    def __init__(self, service: GoogleCalendarService = None):
        self._service = service or GoogleCalendarService()
        
    async def get_upcoming_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieves upcoming calendar items (e.g. from Google Calendar) for tracking availability.
        """
        logger.info(f"[CalendarSkill] Fetching events for the next {days} days.")
        return await self._service.get_upcoming_events(days)

    async def schedule_meeting(self, title: str, start_time: str, duration_minutes: int, attendees: List[str] = None) -> Dict[str, Any]:
        """
        Schedules a calendar event.
        """
        logger.info(f"[CalendarSkill] Creating event: {title} at {start_time}")
        return await self._service.create_event(title, start_time, duration_minutes, attendees or [])

calendar_skill = CalendarSkill()
