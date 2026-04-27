"""Butler-native basic tools.

All direct-implementation tools accept ``input_data: dict[str, Any]`` as their
sole positional argument so the tool registry and governance layer can invoke
every tool through the same uniform call-site.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


async def get_time_tool(input_data: dict[str, Any]) -> dict[str, Any]:
    """Return the current date and time.

    Args:
        input_data: Dict with optional ``timezone`` key (IANA tz string).
                    Defaults to ``"UTC"`` when absent or invalid.

    Returns:
        Dict with ``timezone``, ``iso``, ``date``, ``time``, ``weekday``, ``unix_ms``.
    """
    raw_tz = str(input_data.get("timezone") or "").strip()
    tz_name = raw_tz or "UTC"

    try:
        tz: Any = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz_name = "UTC"
        tz = UTC

    now = datetime.now(tz)
    return {
        "timezone": tz_name,
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "unix_ms": int(now.timestamp() * 1000),
    }