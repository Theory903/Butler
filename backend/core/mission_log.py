"""Butler Mission Log — core renderer.

Three-tier hierarchy:
  T1 SUMMARY    — One line per event. Always visible.
  T2 NARRATIVE  — Lifecycle tree. Pretty / Verbose mode.
  T3 DIAGNOSTIC — Full detail dict. Verbose mode only.

Glyph vocabulary (frozen — never change without a migration note):
  ◈  REQUEST    entry point / boot start
  ◎  ORCHESTRATE internal system phase
  ◉  STAGE_OK   stage completed successfully
  ◌  PASSIVE    background info, no action needed
  ⧖  WAITING    pending external dependency
  ⚑  APPROVAL   human decision gate
  ⚠  DEGRADED   non-ideal but controlled
  ⛔  BLOCKED    policy / safety denied
  ✕  FAILED     demands immediate attention
  ↺  RECOVERED  retry / fallback succeeded
  ◆  COMPLETE   terminal state — request finished
  ♥  HEALTH     system pulse

Modes (BUTLER_LOG_MODE env var):
  pretty   default operator console  — boot tree, health clusters, ANSI colours
  verbose  pretty + T3 detail        — full key/value expansion per event
  minimal  one line per event        — ideal for high-volume prod / log shipper
  json     newline-delimited JSON    — ECS-compatible, no ANSI, stable schema
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ─── Enumerations ──────────────────────────────────────────────────────────────


class DisplayMode(Enum):
    MINIMAL = "minimal"
    PRETTY = "pretty"
    VERBOSE = "verbose"
    JSON = "json"


class Tier(Enum):
    SUMMARY = 1  # always rendered
    NARRATIVE = 2  # pretty / verbose
    DIAGNOSTIC = 3  # verbose only


class Stage(Enum):
    # Request lifecycle
    REQUEST = "request"
    FORWARD = "forward"
    CLASSIFY = "classify"
    ROUTE = "route"
    PLAN = "plan"
    CONTEXT = "context"
    MODEL = "model"
    REASONING = "reasoning"
    EXECUTION = "execution"
    PERSIST = "persist"
    COMPLETE = "complete"
    # Security / guardrails
    SAFETY = "safety"
    REDACTION = "redaction"
    APPROVAL = "approval"
    POLICY = "policy"
    AUTH = "auth"
    # Tools / integrations
    TOOLS = "tools"
    MCP = "mcp"
    BROWSER = "browser"
    TERMINAL = "terminal"
    SEARCH = "search"
    DEVICE = "device"
    # Infrastructure / resilience
    FALLBACK = "fallback"
    RETRY = "retry"
    TIMEOUT = "timeout"
    CACHE = "cache"
    HEALTH = "health"
    # System boot
    BOOT = "boot"
    RUNTIME = "runtime"
    SCHEDULER = "scheduler"
    REALTIME = "realtime"
    SYNC = "sync"


class Status(Enum):
    SUCCESS = "success"
    INFO = "info"
    WAITING = "waiting"
    APPROVAL = "approval"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    FAILURE = "failure"
    RECOVERY = "recovery"
    COMPLETE = "complete"


class Latency(Enum):
    FAST = "fast"  # < 800 ms
    STEADY = "steady"  # 800 ms – 2.5 s
    SLOW = "slow"  # 2.5 s – 7 s
    STALLED = "stalled"  # > 7 s


# ─── Latency helpers ───────────────────────────────────────────────────────────

_LATENCY_BANDS: list[tuple[int, Latency]] = [
    (800, Latency.FAST),
    (2500, Latency.STEADY),
    (7000, Latency.SLOW),
]


def classify_latency(ms: int) -> Latency:
    for ceiling, label in _LATENCY_BANDS:
        if ms < ceiling:
            return label
    return Latency.STALLED


def format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


# ─── Glyph resolution ──────────────────────────────────────────────────────────

_STATUS_GLYPHS: dict[Status, str] = {
    Status.FAILURE: "✕",
    Status.RECOVERY: "↺",
    Status.DEGRADED: "⚠",
    Status.WAITING: "⧖",
    Status.APPROVAL: "⚑",
    Status.BLOCKED: "⛔",
}

_STAGE_GLYPHS: dict[Stage, str] = {
    Stage.REQUEST: "◈",
    Stage.BOOT: "◈",
    Stage.COMPLETE: "◆",
    Stage.HEALTH: "♥",
    Stage.ROUTE: "◎",
    Stage.FORWARD: "◎",
    Stage.CLASSIFY: "◎",
    Stage.PLAN: "◎",
}


def resolve_glyph(stage: Stage, status: Status) -> str:
    if status in _STATUS_GLYPHS:
        return _STATUS_GLYPHS[status]
    if status == Status.COMPLETE:
        return "◆"
    if status == Status.INFO:
        return _STAGE_GLYPHS.get(stage, "◌")
    return _STAGE_GLYPHS.get(stage, "◉")


# ─── ANSI palette ──────────────────────────────────────────────────────────────


class _C:
    """ANSI escape constants. Use _nc() to check before applying."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    # Standard bright
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # 256-colour accents (widely supported: xterm-256, iTerm2, most modern terminals)
    TEAL = "\033[38;5;80m"
    PEACH = "\033[38;5;216m"
    LAVENDER = "\033[38;5;183m"
    ROSE = "\033[38;5;211m"
    GOLD = "\033[38;5;220m"
    SLATE = "\033[38;5;245m"
    DARK_GREY = "\033[38;5;238m"
    MINT = "\033[38;5;121m"

    LATENCY: dict[Latency, str] = {
        Latency.FAST: "\033[92m",  # green
        Latency.STEADY: "\033[38;5;245m",  # slate
        Latency.SLOW: "\033[93m",  # yellow
        Latency.STALLED: "\033[91m",  # red
    }

    STATUS: dict[Status, str] = {
        Status.SUCCESS: "\033[92m",
        Status.INFO: "\033[38;5;245m",
        Status.WAITING: "\033[96m",
        Status.APPROVAL: "\033[95m",
        Status.DEGRADED: "\033[93m",
        Status.BLOCKED: "\033[91m",
        Status.FAILURE: "\033[91m",
        Status.RECOVERY: "\033[92m",
        Status.COMPLETE: "\033[38;5;183m",  # lavender
    }

    STAGE: dict[Stage, str] = {
        Stage.BOOT: "\033[96m",  # cyan
        Stage.RUNTIME: "\033[95m",  # magenta
        Stage.HEALTH: "\033[91m",  # red
        Stage.SCHEDULER: "\033[94m",  # blue
        Stage.REALTIME: "\033[96m",
        Stage.SYNC: "\033[92m",
        Stage.MCP: "\033[38;5;80m",  # teal
        Stage.COMPLETE: "\033[38;5;183m",
        Stage.REQUEST: "\033[94m",
        Stage.MODEL: "\033[38;5;216m",  # peach
        Stage.TOOLS: "\033[38;5;80m",
        Stage.SAFETY: "\033[93m",
        Stage.AUTH: "\033[38;5;216m",
        Stage.EXECUTION: "\033[92m",
        Stage.ROUTE: "\033[94m",
        Stage.FALLBACK: "\033[93m",
        Stage.RETRY: "\033[93m",
        Stage.TIMEOUT: "\033[91m",
    }


def _nc() -> bool:
    """True when colour should be suppressed."""
    if os.environ.get("NO_COLOR") or os.environ.get("BUTLER_LOG_COLOR") == "false":
        return True
    # JSON mode never colours; caller should already handle this
    return not sys.stdout.isatty()


def _stage_color(stage: Stage, no_color: bool) -> str:
    if no_color:
        return ""
    return _C.STAGE.get(stage, _C.WHITE)


def _status_color(status: Status, no_color: bool) -> str:
    if no_color:
        return ""
    return _C.STATUS.get(status, _C.WHITE)


def _reset(no_color: bool) -> str:
    return "" if no_color else _C.RESET


def _dim(no_color: bool) -> str:
    return "" if no_color else _C.DIM


def _bold(no_color: bool) -> str:
    return "" if no_color else _C.BOLD


# ─── Event schema ──────────────────────────────────────────────────────────────


@dataclass
class MissionEvent:
    """Canonical log event consumed by both console renderer and JSON output."""

    schema_version: str = "1.0"
    event_key: str = ""
    stage: Stage = Stage.REQUEST
    status: Status = Status.INFO
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"

    # Correlation
    request_id: str = ""
    trace_id: str | None = None
    span_id: str | None = None
    session_id: str = ""

    # Timing
    timestamp_iso: str = ""
    duration_ms: int | None = None

    # Rendering hints
    ux_hint: str = "default"
    tier: Tier = Tier.NARRATIVE

    # Host context (set by logging config)
    service: str = ""
    environment: str = ""
    node_id: str = ""
    version: str = ""

    @property
    def glyph(self) -> str:
        return resolve_glyph(self.stage, self.status)

    @property
    def latency(self) -> Latency | None:
        if self.duration_ms is None:
            return None
        return classify_latency(self.duration_ms)

    @property
    def ts_short(self) -> str:
        """HH:MM:SS extracted from ISO timestamp."""
        ts = self.timestamp_iso
        if len(ts) >= 19:
            return ts[11:19]
        return ts


# ─── Tree line helpers ─────────────────────────────────────────────────────────


def _tree_branch(
    glyph: str,
    stage: Stage,
    status: Status,
    summary: str,
    right: str = "",
    connector: str = "├─",
    no_color: bool = False,
) -> str:
    sc = _stage_color(stage, no_color)
    r = _reset(no_color)
    d = _dim(no_color)
    label = stage.value.upper().ljust(11)
    right_part = f"  {d}{right}{r}" if right else ""
    return f"           {connector} {glyph} {sc}{label}{r}  {summary}{right_part}"


def _tree_sub(text: str, connector: str = "│    └─", no_color: bool = False) -> str:
    d = _dim(no_color)
    r = _reset(no_color)
    return f"           {connector} {d}{text}{r}"


# ─── Right-side metadata formatter ────────────────────────────────────────────


def _right_meta(event: MissionEvent, no_color: bool) -> str:
    parts: list[str] = []

    if event.duration_ms is not None:
        lat = classify_latency(event.duration_ms)
        lc = _C.LATENCY.get(lat, "") if not no_color else ""
        r = _reset(no_color)
        parts.append(f"{lc}{format_duration(event.duration_ms)}  {lat.value}{r}")

    d = _dim(no_color)
    r = _reset(no_color)
    if event.request_id:
        parts.append(f"{d}req:{event.request_id}{r}")
    if event.trace_id:
        parts.append(f"{d}trace:{event.trace_id[:8]}{r}")
    if event.node_id:
        parts.append(f"{d}node:{event.node_id}{r}")

    return "  ".join(parts)


# ─── ECS-compatible JSON schema ────────────────────────────────────────────────


def _to_ecs_json(event: MissionEvent) -> str:
    """Elastic Common Schema (ECS) 8.x compatible JSON log line.

    Fields:
      @timestamp, log.level, log.logger, message        — ECS base
      event.action, event.category, event.outcome       — ECS event
      labels.*                                           — butler-specific
      tracing.*                                          — ECS tracing
      host.name                                          — ECS host
    """
    payload: dict[str, Any] = {
        "@timestamp": event.timestamp_iso,
        "schema_version": event.schema_version,
        # ECS log
        "log": {
            "level": event.severity,
        },
        # ECS message
        "message": event.summary,
        # ECS event
        "event": {
            "action": event.event_key,
            "category": event.stage.value,
            "outcome": event.status.value,
        },
        # Butler-specific
        "butler": {
            "glyph": event.glyph,
            "stage": event.stage.value,
            "status": event.status.value,
            "tier": event.tier.value,
            "environment": event.environment,
            "node_id": event.node_id,
            "service": event.service,
            "version": event.version,
        },
        # Duration
        "duration_ms": event.duration_ms,
        "latency": event.latency.value if event.latency else None,
        # Free-form details
        "details": event.details,
    }

    # Tracing (ECS tracing.*)
    if event.trace_id or event.span_id or event.request_id or event.session_id:
        payload["tracing"] = {
            "trace": {"id": event.trace_id},
            "span": {"id": event.span_id},
            "request": {"id": event.request_id},
            "session": {"id": event.session_id},
        }

    # Host
    if event.node_id:
        payload["host"] = {"name": event.node_id}

    return json.dumps(payload, separators=(",", ":"), default=str)


# ─── Core renderer ─────────────────────────────────────────────────────────────


class MissionLog:
    """Renders MissionEvent objects to terminal or JSON strings.

    Instantiate once per process; call render(event) per event.
    All methods return strings — the caller is responsible for I/O.

    Thread-safe: no mutable state per render call.
    """

    def __init__(self, mode: DisplayMode = DisplayMode.PRETTY) -> None:
        self.mode = mode
        # Force no-colour in JSON mode regardless of tty
        self._nc = True if mode == DisplayMode.JSON else _nc()

    # ── Public API ────────────────────────────────────────────────────────────

    def render(self, event: MissionEvent) -> str:
        match self.mode:
            case DisplayMode.MINIMAL:
                return self._minimal(event)
            case DisplayMode.PRETTY:
                return self._pretty(event)
            case DisplayMode.VERBOSE:
                return self._verbose(event)
            case DisplayMode.JSON:
                return _to_ecs_json(event)

    def render_boot_tree(
        self,
        timestamp: str,
        boot_events: list[MissionEvent],
        environment: str,
        node_id: str,
    ) -> str:
        """Render entire boot sequence as a single grouped tree (T2 NARRATIVE)."""
        lines: list[str] = []
        nc = self._nc

        r = _reset(nc)
        d = _dim(nc)
        bold = _bold(nc)
        cyan = "" if nc else _C.CYAN

        ts_part = f"{d}{timestamp}{r}  " if timestamp else ""
        header_right = f"{d}env:{environment}  node:{node_id}{r}"

        lines.append(f"{ts_part}◈ {cyan}BOOT       {r}  butler system initializing  {header_right}")
        lines.append("           │")

        last_idx = len(boot_events) - 1
        for i, ev in enumerate(boot_events):
            is_last = i == last_idx
            connector = "└─" if is_last else "├─"
            tree_cont = "   " if is_last else "│  "

            sc = _stage_color(ev.stage, nc)
            label = ev.stage.value.upper().ljust(11)
            right = _right_meta(ev, nc)
            rp = f"  {d}{right}{r}" if right else ""

            lines.append(f"           {connector} {ev.glyph} {sc}{label}{r}  {ev.summary}{rp}")

            if self.mode in (DisplayMode.VERBOSE, DisplayMode.PRETTY) and ev.details:
                items = list(ev.details.items())
                for j, (k, v) in enumerate(items):
                    sub = "└─" if j == len(items) - 1 else "├─"
                    lines.append(f"           {tree_cont}    {sub} {d}{k}: {r}{v}")

        return "\n".join(lines)

    def render_health_cluster(
        self,
        count: int,
        node_id: str,
        environment: str = "",
        timestamp: str = "",
        interval: str = "5s",
    ) -> str:
        """Render a collapsed cluster of health heartbeats as a single line."""
        nc = self._nc
        d = _dim(nc)
        r = _reset(nc)
        green = "" if nc else _C.GREEN

        count_str = f" × {count}" if count > 1 else ""
        right = f"  {d}node:{node_id}  interval:{interval}{r}"
        ts_part = f"{d}{timestamp}{r}  " if timestamp else ""
        return f"{ts_part}♥ {green}HEALTH     {r}  butler healthy{count_str}{right}"

    # ── Private renderers ──────────────────────────────────────────────────────

    def _minimal(self, event: MissionEvent) -> str:
        """One compact line. Zero ANSI. Suitable for any log aggregator."""
        dur = f"  {format_duration(event.duration_ms)}" if event.duration_ms else ""
        ts = f"{event.ts_short}  " if event.ts_short else ""
        return f"{ts}{event.glyph} {event.stage.value.upper():<11}  {event.summary}{dur}"

    def _pretty(self, event: MissionEvent) -> str:
        nc = self._nc
        r = _reset(nc)
        d = _dim(nc)
        sc = _stage_color(event.stage, nc)

        label = event.stage.value.upper().ljust(11)
        right = _right_meta(event, nc)
        rp = f"  {d}{right}{r}" if right else ""
        ts = f"{d}{event.ts_short}{r}  " if event.ts_short else ""

        return f"{ts}{event.glyph} {sc}{label}{r}  {event.summary}{rp}"

    def _verbose(self, event: MissionEvent) -> str:
        lines = [self._pretty(event)]
        nc = self._nc
        d = _dim(nc)
        r = _reset(nc)

        if event.details:
            items = list(event.details.items())
            for i, (k, v) in enumerate(items):
                sub = "└─" if i == len(items) - 1 else "├─"
                lines.append(f"    {sub} {d}{k}: {r}{v}")

        # Always show correlation IDs in verbose
        corr: list[str] = []
        if event.request_id:
            corr.append(f"req:{event.request_id}")
        if event.trace_id:
            corr.append(f"trace:{event.trace_id}")
        if event.session_id:
            corr.append(f"session:{event.session_id}")
        if event.environment:
            corr.append(f"env:{event.environment}")
        if event.service:
            corr.append(f"svc:{event.service}")
        if corr:
            lines.append(f"    └─ {d}{chr(32).join(corr)}{r}")

        return "\n".join(lines)
