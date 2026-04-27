"""
Butler-native time tools module.

Provides time-related tools for LLM agents using Butler-native
implementations instead of Hermes dependencies.
"""

import logging
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)


def get_time(tz: str | None = None) -> dict:
    """Get the current time, optionally in a specific timezone.

    Args:
        tz: Optional timezone string (e.g., "UTC", "America/New_York").
             If None, returns UTC time.

    Returns:
        Dictionary with current time information
    """
    try:
        if tz:
            from zoneinfo import ZoneInfo

            tzinfo = ZoneInfo(tz)
            now = datetime.now(tzinfo)
        else:
            now = datetime.now(UTC)

        return {
            "current_time": now.isoformat(),
            "timezone": tz or "UTC",
            "timestamp": now.timestamp(),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
    except Exception as exc:
        logger.error(f"Failed to get time: {exc}")
        return {
            "error": f"Failed to get time: {exc}",
            "current_time": datetime.now(UTC).isoformat(),
            "timezone": "UTC",
        }


def get_date(tz: str | None = None) -> dict:
    """Get the current date, optionally in a specific timezone.

    Args:
        tz: Optional timezone string (e.g., "UTC", "America/New_York").
             If None, returns UTC date.

    Returns:
        Dictionary with current date information
    """
    try:
        if tz:
            from zoneinfo import ZoneInfo

            tzinfo = ZoneInfo(tz)
            now = datetime.now(tzinfo)
        else:
            now = datetime.now(UTC)

        return {
            "current_date": now.date().isoformat(),
            "timezone": tz or "UTC",
            "formatted": now.strftime("%Y-%m-%d"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
        }
    except Exception as exc:
        logger.error(f"Failed to get date: {exc}")
        return {
            "error": f"Failed to get date: {exc}",
            "current_date": datetime.now(UTC).date().isoformat(),
            "timezone": "UTC",
        }
