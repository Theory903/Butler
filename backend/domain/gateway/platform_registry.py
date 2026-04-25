"""Butler Platform Registry — Phase 11, SOLID edition.

Implements IPlatformRegistry. Depends on IPlatformAdapter (D).
Each adapter wraps ONE platform (S).
New platforms extend IPlatformAdapter without modifying the registry (O).
All adapters are substitutable via the protocol (L).
IPlatformAdapter and IPlatformRegistry are small focused interfaces (I).

Architecture:
    ButlerPlatformRegistry
        ├── HermesPlatformAdapterWrapper(telegram)
        ├── HermesPlatformAdapterWrapper(discord)
        ├── HermesPlatformAdapterWrapper(slack)
        ├── ... (all 19 platforms, lazy-loaded)
        └── [future: CustomPlatformAdapter]

All 19 Hermes platforms supported:
    telegram, discord, slack, whatsapp, signal, mattermost, matrix,
    email, sms, dingtalk, feishu, wecom, weixin, qqbot, homeassistant,
    bluebubbles, webhook, api_server

Each adapter is lazy-loaded on first use (not at import time).
Missing optional deps are handled per-adapter — one failure doesn't block others.

Usage:
    registry = make_default_platform_registry()
    adapter  = registry.get("telegram")
    if adapter and adapter.is_available():
        await adapter.send(recipient, content)
"""

from __future__ import annotations

import importlib
from typing import Any

import structlog

from domain.contracts import IPlatformAdapter

logger = structlog.get_logger(__name__)

# All 19 Hermes platform modules (lazy import path)
_PLATFORM_MODULES: dict[str, str] = {
    "telegram": "integrations.hermes.gateway.platforms.telegram",
    "discord": "integrations.hermes.gateway.platforms.discord",
    "slack": "integrations.hermes.gateway.platforms.slack",
    "whatsapp": "integrations.hermes.gateway.platforms.whatsapp",
    "signal": "integrations.hermes.gateway.platforms.signal",
    "mattermost": "integrations.hermes.gateway.platforms.mattermost",
    "matrix": "integrations.hermes.gateway.platforms.matrix",
    "email": "integrations.hermes.gateway.platforms.email",
    "sms": "integrations.hermes.gateway.platforms.sms",
    "dingtalk": "integrations.hermes.gateway.platforms.dingtalk",
    "feishu": "integrations.hermes.gateway.platforms.feishu",
    "wecom": "integrations.hermes.gateway.platforms.wecom",
    "weixin": "integrations.hermes.gateway.platforms.weixin",
    "qqbot": "integrations.hermes.gateway.platforms.qqbot",
    "homeassistant": "integrations.hermes.gateway.platforms.homeassistant",
    "bluebubbles": "integrations.hermes.gateway.platforms.bluebubbles",
    "webhook": "integrations.hermes.gateway.platforms.webhook",
    "api_server": "integrations.hermes.gateway.platforms.api_server",
}

# Per-platform message length caps (Butler layer, not Hermes)
_MAX_MESSAGE_LENGTH: dict[str, int] = {
    "telegram": 4096,
    "discord": 2000,
    "slack": 3000,
    "whatsapp": 4096,
    "signal": 4096,
    "mattermost": 4000,
    "matrix": 4096,
    "email": 50_000,
    "sms": 160,
    "dingtalk": 2000,
    "feishu": 4000,
    "wecom": 2048,
    "weixin": 2048,
    "qqbot": 2000,
    "homeassistant": 1000,
    "bluebubbles": 2000,
    "webhook": 100_000,
    "api_server": 100_000,
}


# ── HermesPlatformAdapterWrapper (S — single platform, lazy load) ─────────────


class HermesPlatformAdapterWrapper:
    """Wraps a single Hermes platform module as a Butler IPlatformAdapter.

    Single responsibility: ONE platform (S).
    Lazy-loaded — module is only imported when first accessed (O).
    Satisfies IPlatformAdapter (L).

    The Hermes platform class convention:
      from platforms.telegram import HermesTelegramPlatform
    Butler renames it internally — Hermes internals never escape.
    """

    def __init__(self, platform_id: str, module_path: str) -> None:
        self._platform_id = platform_id
        self._module_path = module_path
        self._instance: Any | None = None
        self._load_error: str | None = None
        self._loaded = False

    @property
    def platform_id(self) -> str:  # IPlatformAdapter
        return self._platform_id

    @property
    def max_message_length(self) -> int:  # IPlatformAdapter
        return _MAX_MESSAGE_LENGTH.get(self._platform_id, 4096)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            mod = importlib.import_module(self._module_path)
            # Convention: class named Hermes<Title>Platform or <Title>Platform
            title = self._platform_id.title().replace("_", "")
            cls = (
                getattr(mod, f"Hermes{title}Platform", None)
                or getattr(mod, f"{title}Platform", None)
                or getattr(mod, f"Butler{title}Platform", None)
            )
            if cls:
                self._instance = cls()
            else:
                # Fall back to module-level singleton
                self._instance = getattr(mod, "platform", None)
        except Exception as exc:
            self._load_error = str(exc)
            logger.debug(
                "butler_platform_load_failed",
                platform=self._platform_id,
                error=str(exc),
            )

    def is_available(self) -> bool:  # IPlatformAdapter
        self._ensure_loaded()
        if self._instance is None:
            return False
        if hasattr(self._instance, "is_available"):
            try:
                return bool(self._instance.is_available())
            except Exception:
                return False
        return True

    async def send(  # IPlatformAdapter
        self,
        recipient: str,
        content: str,
        **kwargs: Any,
    ) -> bool:
        self._ensure_loaded()
        if self._instance is None:
            logger.warning("butler_platform_send_unavailable", platform=self._platform_id)
            return False

        # Truncate to platform cap
        if len(content) > self.max_message_length:
            content = content[: self.max_message_length - 3] + "..."

        try:
            # Convention: send_message(recipient, content) or send(recipient, content)
            for method in ("send_message", "send", "deliver"):
                fn = getattr(self._instance, method, None)
                if fn is None:
                    continue
                import asyncio

                result = fn(recipient, content, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return bool(result) if result is not None else True
            logger.warning("butler_platform_no_send_method", platform=self._platform_id)
            return False
        except Exception as exc:
            logger.warning(
                "butler_platform_send_failed", platform=self._platform_id, error=str(exc)
            )
            return False

    def raw_instance(self) -> Any | None:
        """Access the underlying Hermes platform object for advanced usage."""
        self._ensure_loaded()
        return self._instance

    def load_error(self) -> str | None:
        self._ensure_loaded()
        return self._load_error


# ── ButlerPlatformRegistry (IPlatformRegistry, DI-friendly) ────────────────────


class ButlerPlatformRegistry:
    """Registry of all Butler platform adapters.

    Depends on IPlatformAdapter list — injected (D).
    Adding new platforms = new IPlatformAdapter, no registry changes (O).
    Implements IPlatformRegistry (L).
    """

    def __init__(self, adapters: list[IPlatformAdapter]) -> None:
        self._adapters: dict[str, IPlatformAdapter] = {a.platform_id: a for a in adapters}

    def register(self, adapter: IPlatformAdapter) -> None:  # IPlatformRegistry
        self._adapters[adapter.platform_id] = adapter
        logger.info("butler_platform_registered", platform=adapter.platform_id)

    def get(self, platform_id: str) -> IPlatformAdapter | None:  # IPlatformRegistry
        return self._adapters.get(platform_id)

    def all_adapters(self) -> list[IPlatformAdapter]:  # IPlatformRegistry
        return list(self._adapters.values())

    def available_adapters(self) -> list[IPlatformAdapter]:  # IPlatformRegistry
        return [a for a in self._adapters.values() if a.is_available()]

    def available_platform_ids(self) -> list[str]:
        return [a.platform_id for a in self.available_adapters()]

    def status(self) -> dict:
        return {
            "total": len(self._adapters),
            "available": len(self.available_adapters()),
            "platforms": [
                {
                    "id": a.platform_id,
                    "available": a.is_available(),
                    "max_len": a.max_message_length,
                }
                for a in self._adapters.values()
            ],
        }


# ── Default factory ───────────────────────────────────────────────────────────


def make_default_platform_registry() -> ButlerPlatformRegistry:
    """Production: all 19 Hermes adapters, lazy-loaded."""
    adapters: list[IPlatformAdapter] = [
        HermesPlatformAdapterWrapper(pid, mod) for pid, mod in _PLATFORM_MODULES.items()
    ]
    return ButlerPlatformRegistry(adapters=adapters)
