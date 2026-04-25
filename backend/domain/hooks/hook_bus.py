"""Butler Hook Bus — Phase 11, SOLID edition.

Implements IHookBus. Depends on IHookLoader (D).
Each loader owns exactly one hook source (S).
New sources extend IHookLoader without modifying ButlerHookBus (O).
All IHookLoader implementations are substitutable (L).
IHookBus / IHookLoader are small separate interfaces (I).

Architecture:
    ButlerHookBus
        ├── BuiltinHookLoader      — always-on observability hooks
        ├── FileSystemHookLoader   — ~/.butler/hooks/
        └── LegacyHermesHookLoader — ~/.hermes/hooks/ (event-remapped)

Event vocabulary remap (Hermes → Butler):
    gateway:startup  → butler:startup
    session:start    → butler:session:start
    session:end      → butler:session:end
    session:reset    → butler:session:reset
    agent:start      → butler:agent:start
    agent:step       → butler:agent:step
    agent:end        → butler:agent:end
    command:*        → butler:command:*

Usage:
    bus = make_default_hook_bus()
    bus.load()
    await bus.emit("butler:agent:start", {"account_id": ..., "session_id": ...})

    # DI / test:
    bus = ButlerHookBus([BuiltinHookLoader()])
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_BUTLER_HOOKS_DIR = Path.home() / ".butler" / "hooks"
_HERMES_HOOKS_DIR = Path.home() / ".hermes" / "hooks"

# Hermes event → Butler canonical
_EVENT_REMAP: dict[str, str] = {
    "gateway:startup": "butler:startup",
    "session:start": "butler:session:start",
    "session:end": "butler:session:end",
    "session:reset": "butler:session:reset",
    "agent:start": "butler:agent:start",
    "agent:step": "butler:agent:step",
    "agent:end": "butler:agent:end",
}

Handler = Callable[[str, dict], Any]


# ── IHookLoader protocol (small, focused — I) ─────────────────────────────────


class IHookLoader:
    """Single responsibility: provide (event_type, handler) pairs from one source."""

    def load(self) -> list[tuple[str, Handler]]:  # (event_type, handler)
        raise NotImplementedError


# ── Builtin hooks (S — each handler does one thing) ──────────────────────────


async def _on_startup(event_type: str, ctx: dict) -> None:
    logger.info("butler_startup_hook_fired", ts=ctx.get("ts"))


async def _on_session_start(event_type: str, ctx: dict) -> None:
    logger.info(
        "butler_session_started",
        account_id=ctx.get("account_id"),
        session_id=ctx.get("session_id"),
    )


async def _on_agent_end(event_type: str, ctx: dict) -> None:
    logger.info(
        "butler_agent_completed",
        account_id=ctx.get("account_id"),
        success=ctx.get("success", True),
        duration_ms=ctx.get("duration_ms"),
    )
    try:
        from core.observability import get_metrics

        get_metrics().record_tool_call("__agent_run__", "L0", bool(ctx.get("success", True)))
    except Exception:
        pass


class BuiltinHookLoader(IHookLoader):
    """Loads always-on observability hooks. No external deps (S, O)."""

    def load(self) -> list[tuple[str, Handler]]:
        return [
            ("butler:startup", _on_startup),
            ("butler:session:start", _on_session_start),
            ("butler:agent:end", _on_agent_end),
        ]


# ── FileSystem loader (O — adds source without changing bus) ──────────────────


class FileSystemHookLoader(IHookLoader):
    """Loads hooks from a directory of HOOK.yaml + handler.py pairs.

    Single responsibility: disk discovery (S).
    remap=True auto-converts Hermes event names to Butler vocabulary.
    """

    def __init__(self, hooks_dir: Path, *, remap: bool = False) -> None:
        self._dir = hooks_dir
        self._remap = remap

    def load(self) -> list[tuple[str, Handler]]:
        results: list[tuple[str, Handler]] = []
        if not self._dir.exists():
            return results

        for hook_dir in sorted(self._dir.iterdir()):
            if not hook_dir.is_dir():
                continue
            manifest_path = hook_dir / "HOOK.yaml"
            handler_path = hook_dir / "handler.py"
            if not manifest_path.exists() or not handler_path.exists():
                continue

            try:
                import yaml

                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    continue

                events: list[str] = manifest.get("events", [])
                if not events:
                    continue
                if self._remap:
                    events = [_EVENT_REMAP.get(e, e) for e in events]

                spec = importlib.util.spec_from_file_location(
                    f"butler_hook_{hook_dir.name}", handler_path
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                handle_fn: Handler | None = getattr(module, "handle", None)
                if handle_fn is None:
                    continue

                for event in events:
                    results.append((event, handle_fn))
                logger.debug("butler_hook_loaded", name=hook_dir.name, events=events)

            except Exception as exc:
                logger.warning("butler_hook_load_failed", hook=hook_dir.name, error=str(exc))

        return results


# ── ButlerHookBus (IHookBus, DI-friendly) ─────────────────────────────────────


class ButlerHookBus:
    """Butler lifecycle event bus.

    Depends ONLY on IHookLoader list — no hardcoded sources (D).
    Adding a new hook source = pass a new IHookLoader (O).
    Implements IHookBus (L).
    """

    def __init__(self, loaders: list[IHookLoader]) -> None:
        self._loaders = loaders
        self._handlers: dict[str, list[Handler]] = {}
        self._loaded = False

    def load(self) -> ButlerHookBus:  # IHookBus — idempotent
        if self._loaded:
            return self
        self._loaded = True

        for loader in self._loaders:
            try:
                pairs = loader.load()
                for event_type, handler in pairs:
                    self._handlers.setdefault(event_type, []).append(handler)
            except Exception as exc:
                logger.warning(
                    "butler_hook_loader_failed",
                    loader=type(loader).__name__,
                    error=str(exc),
                )

        logger.info("butler_hooks_loaded", events=len(self._handlers))
        return self

    async def emit(  # IHookBus
        self,
        event_type: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = dict(context or {})
        ctx.setdefault("ts", time.time())

        # Exact match + wildcard (e.g. "butler:command:*" matches "butler:command:reset")
        handlers = list(self._handlers.get(event_type, []))
        parts = event_type.split(":")
        if len(parts) >= 2:
            wildcard = ":".join(parts[:-1]) + ":*"
            handlers.extend(self._handlers.get(wildcard, []))

        for fn in handlers:
            try:
                result = fn(event_type, ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning(
                    "butler_hook_handler_failed",
                    hook_event=event_type,
                    handler=getattr(fn, "__name__", "?"),
                    error=str(exc),
                )

    def register(self, event_type: str, handler: Handler) -> None:  # IHookBus
        """Programmatic registration — avoids disk for service-layer hooks."""
        self._handlers.setdefault(event_type, []).append(handler)

    def event_names(self) -> list[str]:  # IHookBus
        return sorted(self._handlers.keys())


# ── Default factory ───────────────────────────────────────────────────────────


def make_default_hook_bus() -> ButlerHookBus:
    """Production: builtins + ~/.butler/hooks/ + legacy ~/.hermes/hooks/."""
    return ButlerHookBus(
        loaders=[
            BuiltinHookLoader(),
            FileSystemHookLoader(_BUTLER_HOOKS_DIR, remap=False),
            FileSystemHookLoader(_HERMES_HOOKS_DIR, remap=True),
        ]
    )
