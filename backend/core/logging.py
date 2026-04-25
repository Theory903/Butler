"""Butler logging configuration — wires structlog to the Mission Log renderer.

Usage
-----
Call once at application startup, before any logging occurs:

    from butler.logging_config import setup_logging
    setup_logging(service_name="butler", environment="production")

Or from settings / dependency injection:

    setup_logging(
        service_name = settings.service_name,
        environment  = settings.environment,
        node_id      = settings.node_id,
        version      = settings.version,
        mode         = settings.log_mode,   # "pretty" | "verbose" | "minimal" | "json"
    )

Then anywhere in the codebase:

    from butler.logging_config import get_logger
    log = get_logger(__name__)
    log.info("route_selected", model="gpt-4o", latency_budget_ms=5000)

Modes (BUTLER_LOG_MODE env var or mode= kwarg):
  pretty   → coloured operator console, boot tree, health clusters  [default dev]
  verbose  → pretty + T3 key/value diagnostic detail per event
  minimal  → one compact line per event, no ANSI                    [default prod]
  json     → newline-delimited ECS JSON, no ANSI                    [log shippers]

Noise suppression:
  - sqlalchemy, httpx, uvicorn access, watchfiles → WARNING
  - Boot events are buffered → flushed as single tree on butler_ready
  - Health heartbeats are clustered → one ♥ line per 15-second burst
  - ml_profile_available lines → collapsed into a single RUNTIME summary line
"""

from __future__ import annotations

import atexit
import logging
import sys
import time
from typing import Any

import structlog

from .mission_log import (
    DisplayMode,
    MissionEvent,
    MissionLog,
    Stage,
    Status,
    Tier,
)

# ─── Noisy third-party loggers ─────────────────────────────────────────────────

_SUPPRESS_TO_WARNING: list[str] = [
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "sqlalchemy.orm",
    "sqlalchemy.events",
    "asyncio",
    "httpx",
    "httpcore",
    "openai",
    "anthropic",
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn.config",
    "watchfiles",
    "watchdog",
    "charset_normalizer",
    "urllib3",
    "PIL",
    "fsevents",
    "aiohttp.access",
    "grpc",
    "boto3",
    "botocore",
    "s3transfer",
    "azure.core",
    "google.auth",
]


# ─── Stage / status inference ──────────────────────────────────────────────────

_EVENT_STAGE_MAP: list[tuple[str, Stage, Status]] = [
    # Boot lifecycle
    ("butler_ready", Stage.BOOT, Status.COMPLETE),
    ("butler_starting", Stage.BOOT, Status.INFO),
    ("butler_stopped", Stage.BOOT, Status.INFO),
    ("butler_shutting_down", Stage.BOOT, Status.INFO),
    ("butler_doctor", Stage.BOOT, Status.SUCCESS),
    ("database_connected", Stage.BOOT, Status.SUCCESS),
    ("redis_connected", Stage.BOOT, Status.SUCCESS),
    ("health_agent", Stage.HEALTH, Status.SUCCESS),
    ("health_heartbeat", Stage.HEALTH, Status.SUCCESS),
    ("butler_healthy", Stage.HEALTH, Status.SUCCESS),
    ("global_state_syncer", Stage.SYNC, Status.SUCCESS),
    ("realtime", Stage.REALTIME, Status.SUCCESS),
    ("pubsub", Stage.REALTIME, Status.SUCCESS),
    ("mcp_manifest_empty", Stage.MCP, Status.INFO),
    ("mcp_", Stage.MCP, Status.SUCCESS),
    ("cron_", Stage.SCHEDULER, Status.SUCCESS),
    ("scheduler", Stage.SCHEDULER, Status.SUCCESS),
    ("ml_profile_available", Stage.RUNTIME, Status.INFO),
    ("ml_runtime", Stage.RUNTIME, Status.SUCCESS),
    # Request lifecycle
    ("router", Stage.ROUTE, Status.SUCCESS),
    ("route", Stage.ROUTE, Status.SUCCESS),
    ("routes_loaded", Stage.ROUTE, Status.SUCCESS),
    ("model", Stage.MODEL, Status.INFO),
    ("reasoning", Stage.REASONING, Status.SUCCESS),
    ("tool", Stage.TOOLS, Status.SUCCESS),
    ("execution", Stage.EXECUTION, Status.SUCCESS),
    ("persist", Stage.PERSIST, Status.SUCCESS),
    ("fallback", Stage.FALLBACK, Status.RECOVERY),
    ("retry", Stage.RETRY, Status.RECOVERY),
    ("timeout", Stage.TIMEOUT, Status.DEGRADED),
    ("safety", Stage.SAFETY, Status.INFO),
    ("approval", Stage.APPROVAL, Status.APPROVAL),
    ("auth", Stage.AUTH, Status.INFO),
    # Prometheus / infra
    ("prometheus", Stage.BOOT, Status.INFO),
    ("metrics", Stage.BOOT, Status.INFO),
    # Failures
    ("_failed", Stage.EXECUTION, Status.FAILURE),
    ("_error", Stage.EXECUTION, Status.FAILURE),
    ("error", Stage.EXECUTION, Status.FAILURE),
    ("fail", Stage.EXECUTION, Status.FAILURE),
    # Completion
    ("complete", Stage.COMPLETE, Status.COMPLETE),
    ("started", Stage.BOOT, Status.SUCCESS),
    ("ready", Stage.BOOT, Status.SUCCESS),
]


def _enrich_stage_status(_logger: Any, _method: str, event_dict: dict) -> dict:
    """structlog pre-processor: infer stage & status from event key."""
    if "stage" in event_dict and "status" in event_dict:
        return event_dict

    key = str(event_dict.get("event", "")).lower()

    for fragment, stage, status in _EVENT_STAGE_MAP:
        if fragment in key:
            event_dict.setdefault("stage", stage.value)
            event_dict.setdefault("status", status.value)
            return event_dict

    event_dict.setdefault("stage", "request")
    event_dict.setdefault("status", "info")
    return event_dict


# ─── Boot buffer ───────────────────────────────────────────────────────────────


class _BootBuffer:
    """Accumulate startup events; flush as a single tree on butler_ready.

    - Absorbs every boot-stage event (raises DropEvent per individual line)
    - Collapses ml_profile_available lines into one RUNTIME summary
    - On butler_ready → returns rendered boot tree as a single log output
    """

    _BOOT_STAGES = {
        Stage.BOOT,
        Stage.RUNTIME,
        Stage.SCHEDULER,
        Stage.MCP,
        Stage.REALTIME,
        Stage.SYNC,
        Stage.HEALTH,
    }

    def __init__(self) -> None:
        self._events: list[MissionEvent] = []
        self._profile_count: int = 0
        self._profile_providers: list[str] = []
        self._flushed: bool = False
        self._boot_ts: str = ""
        self._env: str = "production"
        self._node: str = "node-1"

    @property
    def active(self) -> bool:
        return not self._flushed

    def absorb(self, event_dict: dict) -> bool:
        """Return True if absorbed (caller must raise DropEvent)."""
        if self._flushed:
            return False

        key = event_dict.get("event", "")
        stage_str = event_dict.get("stage", "")

        # Capture header context from first boot event
        if not self._boot_ts:
            ts = event_dict.get("timestamp", "")
            self._boot_ts = ts[11:19] if len(ts) >= 19 else ts
            self._env = event_dict.get("environment", "production")
            self._node = event_dict.get("node_id", "node-1")

        # Collapse ML profile noise
        if "ml_profile_available" in key:
            self._profile_count += 1
            p = event_dict.get("provider", "")
            if p:
                self._profile_providers.append(p)
            return True

        if "butler_ready" in key:
            return False  # let flush() handle

        # Buffer remaining boot-stage events
        try:
            stage = Stage(str(stage_str).lower())
        except ValueError:
            stage = Stage.BOOT

        if stage in self._BOOT_STAGES:
            ev = _dict_to_event(event_dict)
            ev = _label_boot_event(ev, key, self._profile_count, self._profile_providers)
            if ev is not None:
                # Replace existing same-stage entry (prefer last / most complete)
                replaced = False
                for i, existing in enumerate(self._events):
                    if existing.stage == ev.stage:
                        self._events[i] = ev
                        replaced = True
                        break
                if not replaced:
                    self._events.append(ev)
            return True

        return False

    def flush(self, renderer: MissionLog) -> str | None:
        self._flushed = True
        if not self._events and self._profile_count == 0:
            return None

        # Runtime summary
        if self._profile_count > 0:
            short = self._profile_providers[:6]
            more = self._profile_count - len(short)
            pstr = "  ".join(short)
            if more > 0:
                pstr += f"  +{more} more"
            self._events.insert(
                0,
                MissionEvent(
                    event_key="ml_runtime_warmed",
                    stage=Stage.RUNTIME,
                    status=Status.SUCCESS,
                    summary="ML runtime warmed",
                    details={"providers": pstr},
                    tier=Tier.NARRATIVE,
                ),
            )

        # READY terminal event
        self._events.append(
            MissionEvent(
                event_key="butler_ready",
                stage=Stage.COMPLETE,
                status=Status.COMPLETE,
                summary="butler is ready",
                tier=Tier.NARRATIVE,
            )
        )

        return renderer.render_boot_tree(
            timestamp=self._boot_ts,
            boot_events=self._events,
            environment=self._env,
            node_id=self._node,
        )


def _label_boot_event(
    ev: MissionEvent,
    key: str,
    profile_count: int,
    providers: list[str],
) -> MissionEvent | None:
    k = key.lower()

    if "ml_runtime" in k:
        return None  # replaced by profile summary

    if (
        "cron_service_started" in k
        or "cron_scheduler" in k
        or ("scheduler" in k and "started" in k)
    ):
        ev.stage = Stage.SCHEDULER
        ev.status = Status.SUCCESS
        ev.summary = "cron scheduler online"
        ev.details = {"jobs": ev.details.get("jobs", "0"), "tz": ev.details.get("tz", "UTC")}
        return ev

    if "mcp_manifest_empty" in k or ("mcp" in k and "manifest" in k):
        ev.stage = Stage.MCP
        ev.status = Status.INFO
        ev.summary = "no manifest found — bridge standing by"
        ev.details = {"path": ev.details.get("path", "/var/butler/data/mcp/manifest.json")}
        return ev

    if "mcp_" in k:
        ev.stage = Stage.MCP
        ev.status = Status.SUCCESS
        ev.summary = "native service bridge registered"
        return ev

    if "realtime" in k or "pubsub" in k:
        ev.stage = Stage.REALTIME
        ev.status = Status.SUCCESS
        ev.summary = "pubsub listener registered"
        return ev

    if "global_state_syncer" in k:
        node = ev.details.get("node_id", "")
        ev.stage = Stage.SYNC
        ev.status = Status.SUCCESS
        ev.summary = "global state syncer online"
        ev.details = {"node": node[:8]} if node else {}
        return ev

    if "health_agent" in k:
        node = ev.details.get("node_id", "node-1")
        ev.stage = Stage.HEALTH
        ev.status = Status.SUCCESS
        ev.summary = "health agent online"
        ev.details = {"node": node}
        return ev

    if "database_connected" in k:
        ev.stage = Stage.BOOT
        ev.status = Status.SUCCESS
        ev.summary = "database connected"
        return ev

    if "redis_connected" in k:
        ev.stage = Stage.BOOT
        ev.status = Status.SUCCESS
        ev.summary = "redis connected"
        return ev

    if "prometheus_metrics" in k or "metrics_initialized" in k:
        ev.stage = Stage.BOOT
        ev.status = Status.INFO
        ev.summary = "prometheus metrics initialized"
        return ev

    if "routes_loaded" in k:
        ev.stage = Stage.ROUTE
        ev.status = Status.SUCCESS
        ev.summary = "routes loaded"
        return ev

    return ev


# ─── Health cluster ────────────────────────────────────────────────────────────


class _HealthCluster:
    """Collapse consecutive health heartbeats into a single summary line."""

    _WINDOW_S = 15  # seconds within which to cluster

    def __init__(self) -> None:
        self._count: int = 0
        self._last_at: float = 0.0
        self._last_ts: str = ""
        self._node: str = "node-1"
        self._env: str = "production"
        self._interval: str = "5s"

    def feed(self, event_dict: dict) -> None:
        now = time.monotonic()
        self._count = self._count + 1 if (now - self._last_at < self._WINDOW_S) else 1
        self._last_at = now
        self._node = event_dict.get("node_id", self._node)
        self._env = event_dict.get("environment", self._env)
        self._interval = event_dict.get("interval", self._interval)
        ts = event_dict.get("timestamp", "")
        self._last_ts = ts[11:19] if len(ts) >= 19 else ts

    def flush_if_pending(self, renderer: MissionLog) -> str | None:
        if self._count == 0:
            return None
        line = renderer.render_health_cluster(
            count=self._count,
            node_id=self._node,
            environment=self._env,
            timestamp=self._last_ts,
            interval=self._interval,
        )
        self._count = 0
        return line


# ─── Dict → MissionEvent ───────────────────────────────────────────────────────

_META_KEYS = frozenset(
    {
        "event",
        "stage",
        "status",
        "level",
        "logger",
        "timestamp",
        "service",
        "environment",
        "node_id",
        "_logger",
        "_record",
        "version",
        "request_id",
        "trace_id",
        "span_id",
        "session_id",
        "duration_ms",
        "tier",
    }
)


def _coerce_tier(raw_tier: Any) -> Tier:
    if isinstance(raw_tier, Tier):
        return raw_tier

    if isinstance(raw_tier, str):
        normalized = raw_tier.strip()
        if normalized.isdigit():
            raw_tier = int(normalized)
        else:
            return Tier.NARRATIVE

    try:
        return Tier(raw_tier)
    except (TypeError, ValueError):
        return Tier.NARRATIVE


def _dict_to_event(event_dict: dict) -> MissionEvent:
    stage_str = event_dict.get("stage", "request")
    status_str = event_dict.get("status", "info")

    try:
        stage = Stage(str(stage_str).lower())
    except ValueError:
        stage = Stage.REQUEST

    try:
        status = Status(str(status_str).lower())
    except ValueError:
        status = Status.INFO

    details = {k: v for k, v in event_dict.items() if k not in _META_KEYS}
    ts = event_dict.get("timestamp", "")

    return MissionEvent(
        event_key=event_dict.get("event", ""),
        stage=stage,
        status=status,
        summary=event_dict.get("message", event_dict.get("event", "")),
        details=details,
        severity=event_dict.get("level", "info"),
        request_id=event_dict.get("request_id", ""),
        trace_id=event_dict.get("trace_id"),
        span_id=event_dict.get("span_id"),
        session_id=event_dict.get("session_id", ""),
        timestamp_iso=ts,
        duration_ms=event_dict.get("duration_ms"),
        tier=_coerce_tier(event_dict.get("tier", 2)),
        service=event_dict.get("service", ""),
        environment=event_dict.get("environment", ""),
        node_id=event_dict.get("node_id", ""),
        version=event_dict.get("version", ""),
    )


# ─── Main structlog processor ──────────────────────────────────────────────────


class MissionLogProcessor:
    """Stateful structlog final-stage processor.

    Responsibilities:
    - Boot buffering → single tree on butler_ready
    - Health clustering → one ♥ line per 15-second burst
    - Normal event rendering (pretty / verbose / minimal / json)

    Returns a string consumed by structlog's PrintLogger (via basicConfig).
    Raises structlog.DropEvent to suppress noise.
    """

    def __init__(self, mode: DisplayMode = DisplayMode.PRETTY) -> None:
        self._renderer = MissionLog(mode)
        self._mode = mode
        self._boot = _BootBuffer()
        self._health = _HealthCluster()
        atexit.register(self._flush_on_exit)

    def _flush_on_exit(self) -> None:
        line = self._health.flush_if_pending(self._renderer)
        if line:
            pass

    def __call__(self, _logger: Any, _method: str, event_dict: dict) -> str:
        key = event_dict.get("event", "")
        stage_str = event_dict.get("stage", "")

        # ── Boot phase ────────────────────────────────────────────────────────
        if self._boot.active:
            if "butler_ready" in key:
                health_line = self._health.flush_if_pending(self._renderer)
                boot_tree = self._boot.flush(self._renderer)
                parts = [p for p in (health_line, boot_tree) if p]
                if parts:
                    return "\n".join(parts)
                raise structlog.DropEvent

            if self._boot.absorb(event_dict):
                raise structlog.DropEvent

        # ── Health clustering ─────────────────────────────────────────────────
        if stage_str == "health" or any(
            w in key for w in ("heartbeat", "health", "butler_healthy")
        ):
            self._health.feed(event_dict)
            raise structlog.DropEvent

        # ── Normal event ──────────────────────────────────────────────────────
        health_prefix = self._health.flush_if_pending(self._renderer)
        event = _dict_to_event(event_dict)
        rendered = self._renderer.render(event)

        if health_prefix:
            return f"{health_prefix}\n{rendered}"

        return rendered


# ─── Public setup ──────────────────────────────────────────────────────────────


def setup_logging(
    service_name: str,
    environment: str,
    node_id: str = "node-1",
    version: str = "",
    mode: str | None = None,
) -> None:
    """Configure structlog + stdlib logging for Butler Mission Log output.

    Parameters
    ----------
    service_name:
        Bound to every log event as `service`. E.g. ``"butler"``.
    environment:
        ``"development"`` enables DEBUG level and defaults to verbose mode.
        Anything else → INFO + minimal (or json if BUTLER_LOG_MODE=json).
    node_id:
        Identifies this instance in clusters. Defaults to ``"node-1"``.
        In Kubernetes, pass ``os.environ["HOSTNAME"]`` (pod name).
    version:
        Application version string, emitted in boot summary and JSON logs.
    mode:
        Override display mode. One of: ``"pretty"``, ``"verbose"``,
        ``"minimal"``, ``"json"``. Defaults to:
        - ``"verbose"``  in development
        - ``"minimal"``  in production (unless BUTLER_LOG_MODE=json)
    """
    import os

    is_dev = environment == "development"
    log_level = logging.DEBUG if is_dev else logging.INFO

    # Suppress noisy third-party loggers
    for name in _SUPPRESS_TO_WARNING:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger().setLevel(logging.WARNING)

    # Resolve display mode
    env_mode = os.environ.get("BUTLER_LOG_MODE", "")
    mode_str = mode or env_mode or ("verbose" if is_dev else "minimal")
    mode_map = {
        "pretty": DisplayMode.PRETTY,
        "verbose": DisplayMode.VERBOSE,
        "minimal": DisplayMode.MINIMAL,
        "json": DisplayMode.JSON,
    }
    display_mode = mode_map.get(mode_str, DisplayMode.PRETTY)

    # Build processor chain
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        _enrich_stage_status,
        MissionLogProcessor(mode=display_mode),  # final — returns string
    ]

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind shared context — available on every subsequent log call
    structlog.contextvars.bind_contextvars(
        service=service_name,
        environment=environment,
        node_id=node_id,
        version=version,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)
