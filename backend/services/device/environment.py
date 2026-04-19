"""EnvironmentService — Ambient Context Provider (v3.1).

Gathers a lightweight EnvironmentSnapshot encapsulating:
- Temporal context  (local time, timezone, weekday, period-of-day)
- Location context  (lat/lon, city, country — requires client to push coords)
- Platform context  (OS, app version, locale)
- System state      (battery %, connectivity — pushed by mobile client)

This snapshot is injected into the Orchestrator system prompt to ground
Butler's responses with real-world context without violating sovereignty:
- NO direct OS calls to the server machine (everything is client-pushed).
- Location is opaque (lat/lon only); geocoding is optional and gated.
- Snapshot is TTL-cached in Redis (default 60 s) per account_id+device_id.

Butler sovereignty rule: EnvironmentService never calls the LLM directly.
It produces a plain dict that the Orchestrator/IntakeProcessor can attach
to the system prompt context block.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_SNAPSHOT_TTL_S = 60   # 1-minute freshness


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class TemporalContext:
    utc_iso: str                  # 2026-04-19T13:00:00Z
    local_iso: str                # 2026-04-19T18:30:00+05:30
    timezone: str                 # Asia/Kolkata
    weekday: str                  # Sunday
    period_of_day: str            # evening  (morning/afternoon/evening/night)
    day_of_week_index: int        # 0=Monday … 6=Sunday
    week_of_year: int


@dataclass
class LocationContext:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: Optional[str] = None
    country: Optional[str] = None
    accuracy_m: Optional[float] = None


@dataclass
class PlatformContext:
    os: str = "unknown"           # ios | android | macos | web
    app_version: str = "unknown"
    locale: str = "en-US"
    device_model: Optional[str] = None


@dataclass
class SystemState:
    battery_pct: Optional[int] = None         # 0–100
    charging: Optional[bool] = None
    connectivity: Optional[str] = None        # wifi | cellular | offline
    is_silent_mode: Optional[bool] = None


@dataclass
class EnvironmentSnapshot:
    account_id: str
    device_id: str
    captured_at_ms: int
    temporal: TemporalContext
    location: LocationContext
    platform: PlatformContext
    system: SystemState

    def to_prompt_block(self) -> str:
        """Render as a compact context block for system prompt injection."""
        t = self.temporal
        lines = [
            f"[Environment]",
            f"Time: {t.local_iso} ({t.timezone}, {t.weekday}, {t.period_of_day})",
        ]
        if self.location.city:
            lines.append(f"Location: {self.location.city}, {self.location.country}")
        if self.platform.os != "unknown":
            lines.append(f"Platform: {self.platform.os} / {self.platform.locale}")
        if self.system.connectivity:
            lines.append(f"Connectivity: {self.system.connectivity}")
        if self.system.battery_pct is not None:
            charging = " (charging)" if self.system.charging else ""
            lines.append(f"Battery: {self.system.battery_pct}%{charging}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return asdict(self)


# ── Service ────────────────────────────────────────────────────────────────────

class EnvironmentService:
    """Ambient context provider for Butler's grounding layer."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_snapshot(
        self,
        account_id: str,
        device_id: str,
        client_push: dict | None = None,
    ) -> EnvironmentSnapshot:
        """Return a fresh (or cached) EnvironmentSnapshot.

        Args:
            account_id: Authenticated Butler account.
            device_id:  Client device identifier.
            client_push: Optional dict pushed by mobile/web client containing
                         keys: timezone, latitude, longitude, city, country,
                               os, app_version, locale, device_model,
                               battery_pct, charging, connectivity, is_silent_mode
        """
        cache_key = f"env_snapshot:{account_id}:{device_id}"

        # 1. Cache hit (60 s freshness window)
        if not client_push:
            cached = await self._redis.get(cache_key)
            if cached:
                try:
                    return self._deserialise(json.loads(cached), account_id, device_id)
                except Exception:
                    pass

        # 2. Build snapshot from client push + server-side temporal
        client = client_push or {}
        snapshot = self._build(account_id, device_id, client)

        # 3. Cache
        try:
            await self._redis.setex(cache_key, _SNAPSHOT_TTL_S, json.dumps(snapshot.as_dict()))
        except Exception as exc:
            logger.warning("env_snapshot_cache_write_failed", error=str(exc))

        return snapshot

    # ── Builders ──────────────────────────────────────────────────────────────

    def _build(self, account_id: str, device_id: str, client: dict) -> EnvironmentSnapshot:
        tz_str = client.get("timezone", "UTC")
        temporal = self._build_temporal(tz_str)

        location = LocationContext(
            latitude=client.get("latitude"),
            longitude=client.get("longitude"),
            city=client.get("city"),
            country=client.get("country"),
            accuracy_m=client.get("accuracy_m"),
        )

        platform = PlatformContext(
            os=client.get("os", "unknown"),
            app_version=client.get("app_version", "unknown"),
            locale=client.get("locale", "en-US"),
            device_model=client.get("device_model"),
        )

        system = SystemState(
            battery_pct=client.get("battery_pct"),
            charging=client.get("charging"),
            connectivity=client.get("connectivity"),
            is_silent_mode=client.get("is_silent_mode"),
        )

        return EnvironmentSnapshot(
            account_id=account_id,
            device_id=device_id,
            captured_at_ms=int(time.time() * 1000),
            temporal=temporal,
            location=location,
            platform=platform,
            system=system,
        )

    @staticmethod
    def _build_temporal(tz_str: str) -> TemporalContext:
        now_utc = datetime.now(timezone.utc)
        try:
            local_tz = ZoneInfo(tz_str)
        except (ZoneInfoNotFoundError, KeyError):
            local_tz = timezone.utc
            tz_str = "UTC"

        now_local = now_utc.astimezone(local_tz)
        hour = now_local.hour
        if 5 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 17:
            period = "afternoon"
        elif 17 <= hour < 21:
            period = "evening"
        else:
            period = "night"

        return TemporalContext(
            utc_iso=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            local_iso=now_local.isoformat(timespec="seconds"),
            timezone=tz_str,
            weekday=now_local.strftime("%A"),
            period_of_day=period,
            day_of_week_index=now_local.weekday(),
            week_of_year=int(now_local.strftime("%W")),
        )

    @staticmethod
    def _deserialise(d: dict, account_id: str, device_id: str) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            account_id=account_id,
            device_id=device_id,
            captured_at_ms=d["captured_at_ms"],
            temporal=TemporalContext(**d["temporal"]),
            location=LocationContext(**d["location"]),
            platform=PlatformContext(**d["platform"]),
            system=SystemState(**d["system"]),
        )
