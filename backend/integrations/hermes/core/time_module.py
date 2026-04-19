"""Butler-adapted Hermes time utilities - timezone-aware clock.

Provides a single `now()` helper that returns a timezone-aware datetime
based on the user's configured IANA timezone.
"""
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

_cached_tz: Optional[ZoneInfo] = None
_cached_tz_name: Optional[str] = None
_cache_resolved: bool = False


def _resolve_timezone_name() -> str:
    tz_env = os.getenv("HERMES_TIMEZONE", "").strip()
    if tz_env:
        return tz_env

    try:
        import yaml
        from backend.integrations.hermes.core.constants import get_config_path

        config_path = get_config_path()
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            tz_cfg = cfg.get("timezone", "")
            if isinstance(tz_cfg, str) and tz_cfg.strip():
                return tz_cfg.strip()
    except Exception:
        pass

    return ""


def _get_zoneinfo(name: str) -> Optional[ZoneInfo]:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (KeyError, Exception) as exc:
        logger.warning(
            "Invalid timezone '%s': %s. Falling back to server local time.",
            name, exc,
        )
        return None


def get_timezone() -> Optional[ZoneInfo]:
    global _cached_tz, _cached_tz_name, _cache_resolved
    if _cache_resolved:
        return _cached_tz

    tz_name = _resolve_timezone_name()
    _cached_tz = _get_zoneinfo(tz_name)
    _cached_tz_name = tz_name
    _cache_resolved = True
    return _cached_tz


def now() -> datetime:
    tz = get_timezone()
    if tz is None:
        return datetime.now().astimezone()
    return datetime.now(tz)


def reset_cache() -> None:
    global _cached_tz, _cached_tz_name, _cache_resolved
    _cached_tz = None
    _cached_tz_name = None
    _cache_resolved = False