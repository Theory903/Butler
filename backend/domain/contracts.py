"""Butler Domain Contracts — Phase 11 (SOLID edition).

All inter-component boundaries are defined here as Protocols.
Nothing in domain/ or services/ imports concrete implementations directly —
only these contracts. This enforces:

  S — each contract has a single responsibility
  O — new implementations extend without modifying callers
  L — all implementations are substitutable for their Protocol
  I — interfaces are small and focused (no fat base classes)
  D — callers depend on Protocol, not the concrete class

Import pattern:
    from domain.contracts import IToolRegistry, IHookBus, ISessionStore
    # Never: from domain.tools.butler_tool_registry import ButlerToolRegistry

Protocols use runtime_checkable so isinstance() works in DI containers.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

# ── Session Store ─────────────────────────────────────────────────────────────

@runtime_checkable
class ISessionStore(Protocol):
    """Conversation turn persistence — append, retrieve, search, delete."""

    @abstractmethod
    async def append_turn(
        self,
        account_id: str,
        session_id: str,
        role: str,
        content: str,
        **kwargs: Any,
    ) -> Any: ...

    @abstractmethod
    async def get_history(
        self,
        account_id: str,
        session_id: str,
        *,
        limit: int = 50,
        reverse: bool = False,
    ) -> list[Any]: ...

    @abstractmethod
    async def search(
        self,
        account_id: str,
        query: str,
        *,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[Any]: ...

    @abstractmethod
    async def delete_session(self, account_id: str, session_id: str) -> int: ...

    @abstractmethod
    async def session_count(self, account_id: str, session_id: str) -> int: ...


# ── Tool Registry ─────────────────────────────────────────────────────────────

@runtime_checkable
class IToolRegistry(Protocol):
    """Tool schema + dispatch surface."""

    @abstractmethod
    def discover(self) -> list[str]: ...

    @abstractmethod
    def get_schemas(self, toolset_filter: list[str] | None = None) -> list[dict]: ...

    @abstractmethod
    def get_capability_for_tool(self, tool_name: str) -> str | None: ...

    @abstractmethod
    async def execute(self, tool_name: str, args: dict[str, Any]) -> str: ...

    @abstractmethod
    def tool_names(self) -> list[str]: ...

    @abstractmethod
    def is_available(self) -> bool: ...


# ── Hook Bus ──────────────────────────────────────────────────────────────────

@runtime_checkable
class IHookBus(Protocol):
    """Lifecycle event bus — emit, register, load."""

    @abstractmethod
    def load(self) -> "IHookBus": ...

    @abstractmethod
    async def emit(
        self, event_type: str, context: dict[str, Any] | None = None
    ) -> None: ...

    @abstractmethod
    def register(self, event_type: str, handler: Any) -> None: ...

    @abstractmethod
    def event_names(self) -> list[str]: ...


# ── Plugin ────────────────────────────────────────────────────────────────────

@runtime_checkable
class IPlugin(Protocol):
    """Minimum contract any Butler plugin must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def plugin_type(self) -> str: ...  # "memory" | "context" | ...

    @abstractmethod
    def is_available(self) -> bool: ...


@runtime_checkable
class IPluginLoader(Protocol):
    """Loads plugins from a source (dir, registry, remote, ...)."""

    @abstractmethod
    async def load(self) -> list[Any]: ...  # list of IPlugin-compatible objects


@runtime_checkable
class IPluginBus(Protocol):
    """Plugin lifecycle manager."""

    @abstractmethod
    async def load_all(self) -> "IPluginBus": ...

    @abstractmethod
    def get(self, name: str) -> Any | None: ...

    @abstractmethod
    def all_plugins(self) -> list[Any]: ...

    @abstractmethod
    def plugins_of_type(self, plugin_type: str) -> list[Any]: ...

    @abstractmethod
    async def teardown_all(self) -> None: ...

    @abstractmethod
    def register(self, name: str, instance: Any, plugin_type: str) -> Any: ...


# ── Skills Catalog ────────────────────────────────────────────────────────────

@runtime_checkable
class ISkillsCatalog(Protocol):
    """Read-only skill discovery surface."""

    @abstractmethod
    def scan(self) -> list[dict]: ...

    @abstractmethod
    def list_skills(self, domain: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_skill(self, name: str) -> dict | None: ...


# ── Platform Adapter ──────────────────────────────────────────────────────────

@runtime_checkable
class IPlatformAdapter(Protocol):
    """Outbound delivery adapter for a single platform channel."""

    @property
    @abstractmethod
    def platform_id(self) -> str: ...

    @property
    @abstractmethod
    def max_message_length(self) -> int: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def send(self, recipient: str, content: str, **kwargs: Any) -> bool: ...


@runtime_checkable
class IPlatformRegistry(Protocol):
    """Registry of all platform adapters."""

    @abstractmethod
    def register(self, adapter: IPlatformAdapter) -> None: ...

    @abstractmethod
    def get(self, platform_id: str) -> IPlatformAdapter | None: ...

    @abstractmethod
    def all_adapters(self) -> list[IPlatformAdapter]: ...

    @abstractmethod
    def available_adapters(self) -> list[IPlatformAdapter]: ...


# ── ACP Bridge ────────────────────────────────────────────────────────────────

@runtime_checkable
class IACPBridge(Protocol):
    """Translates an external approval source into Butler ACP decisions."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def is_running(self) -> bool: ...


# ── Notebook Repository ───────────────────────────────────────────────────────

@runtime_checkable
class INotebookRepository(Protocol):
    """Persistence for research notebooks, sources, and notes."""

    @abstractmethod
    async def create_notebook(self, account_id: str, name: str, description: str = "") -> Any: ...

    @abstractmethod
    async def get_notebooks(self, account_id: str, archived: bool = False) -> list[Any]: ...

    @abstractmethod
    async def get_notebook(self, account_id: str, notebook_id: str) -> Any | None: ...

    @abstractmethod
    async def add_source(self, notebook_id: str, title: str, source_type: str, asset: dict) -> Any: ...

    @abstractmethod
    async def get_sources(self, notebook_id: str) -> list[Any]: ...

    @abstractmethod
    async def add_note(self, notebook_id: str, title: str, content: str, note_type: str = "human") -> Any: ...

    @abstractmethod
    async def get_notes(self, notebook_id: str) -> list[Any]: ...
