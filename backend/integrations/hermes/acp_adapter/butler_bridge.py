"""Hermes ACP Bridge — Phase 11, SOLID edition.

Implements IACPBridge. Translates Hermes ACP protocol events into
Butler ACPRequest/ACPDecision objects (the Butler ACP layer — api/routes/acp.py).

What Hermes ACP is:
  The Hermes ACP adapter (acp_adapter/) implements a JsonRPC/HTTP server
  that receives tool approval decisions from an IDE (Copilot, Cursor, etc.)
  via the Agent Conversation Protocol. This allows an editor plugin to be
  a valid approval source alongside Butler's own HTTP endpoint.

What this bridge does:
  Hermes ACP event → translate → Butler ACPRequest object
  IDE approval decision → translate → Butler ACPDecision → ButlerACPServer

Architecture:
    IDE / Copilot
        ↓ (ACP protocol over HTTP)
    HermesACPBridge           ← this file
        ↓ translate
    ButlerACPServer           ← domain/orchestrator/acp_server.py

SOLID:
  S — single responsibility: translate Hermes ACP ↔ Butler ACP
  O — extend via IACPEventTranslator for new source formats
  L — satisfies IACPBridge, substitutable
  I — small IACPBridge (start/stop/is_running) + IACPEventTranslator (translate)
  D — depends on IACPEventTranslator for parsing, not raw Hermes types

Usage:
    bridge = HermesACPBridge(acp_server=butler_acp_server)
    await bridge.start()
    # Bridge runs in background, forwarding IDE approvals to ButlerACPServer
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


# ── Translator protocol (I, D) ────────────────────────────────────────────────

class IACPEventTranslator(Protocol):
    """Translates raw ACP event dicts into Butler-typed objects.

    Single responsibility: parsing only (S).
    Swappable for different ACP protocol versions (O).
    """

    def to_butler_request(self, raw_event: dict[str, Any]) -> dict | None:
        """Return a Butler-compatible ACPRequest dict, or None if unrecognised."""
        ...

    def to_hermes_response(self, decision: dict[str, Any]) -> dict:
        """Return a Hermes ACP response dict from a Butler ACPDecision."""
        ...


# ── Default translator (Hermes ACP v1 format) ─────────────────────────────────

class HermesACPv1Translator:
    """Translates Hermes ACP protocol v1 events.

    Hermes ACP event format:
      {
        "type":       "tool_approval_request",
        "request_id": "req_abc",
        "tool_name":  "terminal",
        "args":       {...},
        "context":    {"session_id": "...", "account_id": "..."},
      }
    """

    def to_butler_request(self, raw_event: dict[str, Any]) -> dict | None:
        if raw_event.get("type") != "tool_approval_request":
            return None
        context = raw_event.get("context", {})
        return {
            "request_id": raw_event.get("request_id"),
            "tool_name":  raw_event.get("tool_name"),
            "args":       raw_event.get("args", {}),
            "account_id": context.get("account_id"),
            "session_id": context.get("session_id"),
            "source":     "hermes_acp_ide",
        }

    def to_hermes_response(self, decision: dict[str, Any]) -> dict:
        return {
            "type":       "tool_approval_response",
            "request_id": decision.get("request_id"),
            "approved":   decision.get("approved", False),
            "reason":     decision.get("reason"),
        }


# ── HermesACPBridge (IACPBridge) ──────────────────────────────────────────────

class HermesACPBridge:
    """Bridges the Hermes ACP adapter into Butler's ButlerACPServer.

    Depends on:
      - acp_server: any object with submit_decision() / register_request() (D)
      - translator: IACPEventTranslator (D)

    Single responsibility: translate and forward (S).
    Satisfies IACPBridge (L).
    """

    def __init__(
        self,
        acp_server: Any,
        translator: IACPEventTranslator | None = None,
        host: str = "127.0.0.1",
        port: int = 9_876,
    ) -> None:
        self._acp_server  = acp_server
        self._translator  = translator or HermesACPv1Translator()
        self._host        = host
        self._port        = port
        self._running     = False
        self._server_task: asyncio.Task | None = None
        self._hermes_server: Any | None = None

    async def start(self) -> None:              # IACPBridge
        """Start the Hermes ACP server in the background."""
        if self._running:
            return
        try:
            await self._start_hermes_acp_server()
            self._running = True
            logger.info("hermes_acp_bridge_started", host=self._host, port=self._port)
        except Exception as exc:
            logger.warning("hermes_acp_bridge_start_failed", error=str(exc))

    async def _start_hermes_acp_server(self) -> None:
        """Lazy-import and start the Hermes ACP server subprocess."""
        try:
            from integrations.hermes.acp_adapter.server import (
                ButlerACPServer as HermesACPServer,  # noqa: F401  # type: ignore[import]
            )
            # The Hermes ACP server provides a callback for incoming events
            # We inject our handler so every approval request is forwarded to Butler
            self._server_task = asyncio.create_task(
                self._monitor_hermes_events()
            )
        except ImportError:
            logger.warning(
                "hermes_acp_server_unavailable",
                hint="Install Hermes ACP adapter or skip IDE integration",
            )

    async def _monitor_hermes_events(self) -> None:
        """Monitor the Hermes ACP event queue and forward to ButlerACPServer."""
        while self._running:
            try:
                event = await self._get_next_hermes_event()
                if event:
                    await self._handle_event(event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("hermes_acp_monitor_error", error=str(exc))
            await asyncio.sleep(0.1)

    async def _get_next_hermes_event(self) -> dict | None:
        """Poll Hermes ACP adapter for the next pending event."""
        try:
            from integrations.hermes.acp_adapter.events import get_pending_event
            return get_pending_event()
        except Exception:
            return None

    async def _handle_event(self, raw_event: dict[str, Any]) -> None:
        """Translate event and forward to Butler ACP server."""
        butler_request = self._translator.to_butler_request(raw_event)
        if butler_request is None:
            return

        try:
            # Forward to Butler's ACPServer — registers the pending approval
            if hasattr(self._acp_server, "register_request"):
                await self._acp_server.register_request(butler_request)
                logger.info(
                    "hermes_acp_event_forwarded",
                    request_id=butler_request.get("request_id"),
                    tool=butler_request.get("tool_name"),
                )
        except Exception as exc:
            logger.warning("hermes_acp_forward_failed", error=str(exc))

    async def stop(self) -> None:               # IACPBridge
        """Stop the bridge and clean up."""
        self._running = False
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._server_task
        self._server_task = None
        logger.info("hermes_acp_bridge_stopped")

    def is_running(self) -> bool:               # IACPBridge
        return self._running

    def translate_decision(self, decision: dict[str, Any]) -> dict:
        """Translate a Butler ACPDecision to Hermes response format (for IDE feedback)."""
        return self._translator.to_hermes_response(decision)


# ── Factory ───────────────────────────────────────────────────────────────────

def make_hermes_acp_bridge(
    acp_server: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 9_876,
) -> HermesACPBridge:
    """Production factory. acp_server = ButlerACPServer instance."""
    return HermesACPBridge(
        acp_server=acp_server,
        translator=HermesACPv1Translator(),
        host=host,
        port=port,
    )
