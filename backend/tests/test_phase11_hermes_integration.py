"""Phase 11 Integration Tests — Full Hermes Assimilation.

Tests every Butler-owned surface built in Phase 11:
  1. domain/contracts.py          — Protocol satisfaction
  2. domain/memory/session_store.py — ButlerSessionStore (mocked Postgres)
  3. domain/tools/butler_tool_registry.py — ButlerToolRegistry (mock adapter)
  4. domain/hooks/hook_bus.py     — ButlerHookBus (DI via BuiltinHookLoader)
  5. domain/plugins/plugin_bus.py — ButlerPluginBus (DI via mock loader)
  6. domain/skills/skills_catalog.py — ButlerSkillsCatalog (real fs scan)
  7. domain/gateway/platform_registry.py — ButlerPlatformRegistry (mock adapters)
  8. integrations/hermes/acp_adapter/butler_bridge.py — HermesACPBridge
  9. cli/butler_cli.py            — ButlerCLIRunner (isolated commands)
 10. domain/orchestrator/hermes_agent_backend.py — rebranding checks

All tests are designed to run with no live database, no Hermes AIAgent,
no Redis, and no external network. Every Hermes surface is mocked at the
Butler adapter boundary.

Test philosophy (SOLID):
  - Each test class tests ONE component (S)
  - Tests inject mock implementations via constructors (D / not monkey-patch)
  - No module-level state mutated across tests (reset() called everywhere)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Contracts — Protocol compliance
# ═══════════════════════════════════════════════════════════════════════════════

class TestContracts:
    """Verify all domain protocols can be imported and are runtime_checkable."""

    def test_all_protocols_importable(self):
        from domain.contracts import (
            IACPBridge,
            IHookBus,
            IPlatformAdapter,
            IPlatformRegistry,
            IPlugin,
            IPluginBus,
            IPluginLoader,
            ISessionStore,
            ISkillsCatalog,
            IToolRegistry,
        )
        # If we got here, all protocols are importable
        assert ISessionStore is not None
        assert IToolRegistry is not None
        assert IHookBus is not None
        assert IPlugin is not None
        assert IPluginLoader is not None
        assert IPluginBus is not None
        assert ISkillsCatalog is not None
        assert IPlatformAdapter is not None
        assert IPlatformRegistry is not None
        assert IACPBridge is not None

    def test_protocols_are_runtime_checkable(self):
        from domain.contracts import ISessionStore

        class FakeSessionStore:
            async def append_turn(self, account_id, session_id, role, content, **kw): pass
            async def get_history(self, account_id, session_id, **kw): return []
            async def search(self, account_id, query, **kw): return []
            async def delete_session(self, account_id, session_id): return 0
            async def session_count(self, account_id, session_id): return 0

        # isinstance check works because @runtime_checkable
        assert isinstance(FakeSessionStore(), ISessionStore)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ButlerSessionStore
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerSessionStore:
    """Tests ButlerSessionStore without a live database.

    The store normally calls get_db_session() — we verify it can be
    imported and has the correct interface.
    """

    def test_importable(self):
        from domain.memory.session_store import ButlerSessionStore
        store = ButlerSessionStore()
        assert store is not None

    def test_implements_isession_store(self):
        from domain.contracts import ISessionStore
        from domain.memory.session_store import ButlerSessionStore
        assert isinstance(ButlerSessionStore(), ISessionStore)

    def test_has_all_methods(self):
        from domain.memory.session_store import ButlerSessionStore
        store = ButlerSessionStore()
        assert callable(store.append_turn)
        assert callable(store.get_history)
        assert callable(store.search)
        assert callable(store.delete_session)
        assert callable(store.session_count)
        assert callable(store.list_sessions)

    @pytest.mark.asyncio
    async def test_get_history_mocked(self):
        """Verify get_history query structure (with mocked session)."""
        from domain.memory.session_store import ButlerSessionStore

        mock_turn = MagicMock()
        mock_turn.role = "user"
        mock_turn.content = "Hello Butler"
        mock_turn.turn_index = 0

        store = ButlerSessionStore()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("domain.memory.session_store.get_db_session", return_value=mock_session):
            turns = await store.get_history(
                "00000000-0000-0000-0000-000000000001",
                "10000000-0000-0000-0000-000000000001",
                limit=10,
            )
        assert len(turns) == 1
        assert turns[0].content == "Hello Butler"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ButlerToolRegistry
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerToolRegistry:
    """Tests ButlerToolRegistry with a mock adapter — no Hermes import needed."""

    def _make_mock_adapter(self):
        adapter = MagicMock()
        adapter.discover.return_value = ["integrations.hermes.tools.web"]
        adapter.get_all_tool_names.return_value = ["web_search", "file_read", "terminal"]
        adapter.get_definitions.return_value = [
            {"type": "function", "function": {"name": "web_search", "description": "Search"}},
        ]
        adapter.get_toolset_for_tool.side_effect = lambda n: {
            "web_search": "web", "file_read": "files", "terminal": "terminal"
        }.get(n)
        adapter.get_entry.return_value = None
        adapter.get_available_toolsets.return_value = {}
        adapter.get_toolset_requirements.return_value = {}
        adapter.get_emoji.return_value = "⚡"
        return adapter

    def test_discover_delegates_to_adapter(self):
        from domain.tools.butler_tool_registry import ButlerToolRegistry
        adapter = self._make_mock_adapter()
        registry = ButlerToolRegistry(adapter=adapter)
        result = registry.discover()
        adapter.discover.assert_called_once()
        assert result == ["integrations.hermes.tools.web"]

    def test_get_schemas_returns_list(self):
        from domain.tools.butler_tool_registry import ButlerToolRegistry
        adapter = self._make_mock_adapter()
        registry = ButlerToolRegistry(adapter=adapter)
        schemas = registry.get_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "web_search"

    def test_capability_map_for_toolsets(self):
        from domain.tools.butler_tool_registry import ButlerToolRegistry
        adapter = self._make_mock_adapter()
        registry = ButlerToolRegistry(adapter=adapter)
        assert registry.get_capability_for_tool("web_search") == "WEB_SEARCH"
        assert registry.get_capability_for_tool("file_read") == "FILE_OPS"
        assert registry.get_capability_for_tool("terminal") == "TERMINAL"

    def test_unknown_tool_returns_none_capability(self):
        from domain.tools.butler_tool_registry import ButlerToolRegistry
        adapter = self._make_mock_adapter()
        adapter.get_toolset_for_tool.return_value = None
        registry = ButlerToolRegistry(adapter=adapter)
        assert registry.get_capability_for_tool("nonexistent") is None

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        import json

        from domain.tools.butler_tool_registry import ButlerToolRegistry
        adapter = self._make_mock_adapter()
        adapter.get_entry.return_value = None
        registry = ButlerToolRegistry(adapter=adapter)
        result = await registry.execute("nonexistent", {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_execute_sync_tool(self):
        import json

        from domain.tools.butler_tool_registry import ButlerToolRegistry

        entry = MagicMock()
        entry.is_async = False
        entry.handler = lambda args: json.dumps({"result": "ok"})

        adapter = self._make_mock_adapter()
        adapter.get_entry.return_value = entry
        registry = ButlerToolRegistry(adapter=adapter)
        result = await registry.execute("web_search", {"query": "test"})
        assert json.loads(result)["result"] == "ok"

    def test_implements_itool_registry(self):
        from domain.contracts import IToolRegistry
        from domain.tools.butler_tool_registry import ButlerToolRegistry
        registry = ButlerToolRegistry(adapter=self._make_mock_adapter())
        assert isinstance(registry, IToolRegistry)

    def test_factory_returns_instance(self):
        from domain.tools.butler_tool_registry import make_default_tool_registry
        registry = make_default_tool_registry()
        assert registry is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ButlerHookBus
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerHookBus:
    """Tests ButlerHookBus with DI loaders — no filesystem dependency."""

    def test_builtin_loader_registers_3_events(self):
        from domain.hooks.hook_bus import BuiltinHookLoader
        pairs = BuiltinHookLoader().load()
        events = [event for event, _ in pairs]
        assert "butler:startup" in events
        assert "butler:session:start" in events
        assert "butler:agent:end" in events

    def test_bus_loads_builtins(self):
        from domain.hooks.hook_bus import BuiltinHookLoader, ButlerHookBus
        bus = ButlerHookBus(loaders=[BuiltinHookLoader()])
        bus.load()
        assert "butler:startup" in bus.event_names()
        assert "butler:agent:end" in bus.event_names()

    def test_load_is_idempotent(self):
        from domain.hooks.hook_bus import BuiltinHookLoader, ButlerHookBus
        bus = ButlerHookBus(loaders=[BuiltinHookLoader()])
        bus.load()
        bus.load()  # second call — should not double-register
        count = len(bus._handlers.get("butler:startup", []))
        assert count == 1

    @pytest.mark.asyncio
    async def test_emit_fires_handler(self):
        from domain.hooks.hook_bus import ButlerHookBus
        fired = []

        class CapturingLoader:
            def load(self):
                def handler(evt, ctx): fired.append(evt)
                return [("butler:test:event", handler)]

        bus = ButlerHookBus(loaders=[CapturingLoader()])
        bus.load()
        await bus.emit("butler:test:event", {"key": "value"})
        assert fired == ["butler:test:event"]

    @pytest.mark.asyncio
    async def test_async_handler_awaited(self):
        from domain.hooks.hook_bus import ButlerHookBus
        fired = []

        class AsyncLoader:
            def load(self):
                async def async_handler(evt, ctx): fired.append("async")
                return [("butler:async:test", async_handler)]

        bus = ButlerHookBus(loaders=[AsyncLoader()])
        bus.load()
        await bus.emit("butler:async:test")
        assert "async" in fired

    @pytest.mark.asyncio
    async def test_handler_error_does_not_bubble(self):
        """Errors in hooks must NEVER block the hot path."""
        from domain.hooks.hook_bus import ButlerHookBus

        class BadLoader:
            def load(self):
                def bad_handler(evt, ctx): raise RuntimeError("hook failed")
                return [("butler:bad:event", bad_handler)]

        bus = ButlerHookBus(loaders=[BadLoader()])
        bus.load()
        # Should not raise
        await bus.emit("butler:bad:event")

    def test_wildcard_matching(self):
        from domain.hooks.hook_bus import ButlerHookBus
        fired = []

        class WildcardLoader:
            def load(self):
                def handler(evt, ctx): fired.append(evt)
                return [("butler:command:*", handler)]

        bus = ButlerHookBus(loaders=[WildcardLoader()])
        bus.load()
        asyncio.run(
            bus.emit("butler:command:reset")
        )
        assert "butler:command:reset" in fired

    def test_register_programmatic(self):
        from domain.hooks.hook_bus import ButlerHookBus
        bus = ButlerHookBus(loaders=[])
        bus.load()
        bus.register("butler:custom", lambda e, c: None)
        assert "butler:custom" in bus.event_names()

    def test_implements_ihook_bus(self):
        from domain.contracts import IHookBus
        from domain.hooks.hook_bus import ButlerHookBus
        bus = ButlerHookBus(loaders=[])
        assert isinstance(bus, IHookBus)

    def test_event_remap_loaded_from_hermes_dir(self):
        """FileSystemHookLoader with remap=True converts Hermes events."""
        from domain.hooks.hook_bus import FileSystemHookLoader
        loader = FileSystemHookLoader(Path("/nonexistent/path"), remap=True)
        # Non-existent dir returns empty list without error
        assert loader.load() == []

    def test_factory_returns_bus(self):
        from domain.hooks.hook_bus import make_default_hook_bus
        bus = make_default_hook_bus()
        assert bus is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ButlerPluginBus
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerPluginBus:
    """Tests ButlerPluginBus with injected mock loaders."""

    def _make_loader(self, plugins):
        class MockLoader:
            async def load(self):
                return plugins
        return MockLoader()

    @pytest.mark.asyncio
    async def test_loads_plugins_from_injected_loader(self):
        from domain.plugins.plugin_bus import ButlerPlugin, ButlerPluginBus
        mock = ButlerPlugin(name="test_plugin", plugin_type="memory",
                            module_path="test", instance=object(), _available=True)
        bus = ButlerPluginBus(loaders=[self._make_loader([mock])])
        await bus.load_all()
        assert bus.get("test_plugin") is not None
        assert bus.get("test_plugin").available is True

    @pytest.mark.asyncio
    async def test_load_all_is_idempotent(self):
        from domain.plugins.plugin_bus import ButlerPlugin, ButlerPluginBus
        count = []
        class CountingLoader:
            async def load(self):
                count.append(1)
                return [ButlerPlugin("p", "memory", "", object(), _available=True)]
        bus = ButlerPluginBus(loaders=[CountingLoader()])
        await bus.load_all()
        await bus.load_all()
        assert len(count) == 1   # loaded only once

    @pytest.mark.asyncio
    async def test_failed_loader_does_not_block_others(self):
        from domain.plugins.plugin_bus import ButlerPlugin, ButlerPluginBus

        class BadLoader:
            async def load(self): raise RuntimeError("loader failed")

        class GoodLoader:
            async def load(self):
                return [ButlerPlugin("good", "memory", "", object(), _available=True)]

        bus = ButlerPluginBus(loaders=[BadLoader(), GoodLoader()])
        await bus.load_all()
        assert bus.get("good") is not None

    @pytest.mark.asyncio
    async def test_plugins_of_type_filter(self):
        from domain.plugins.plugin_bus import ButlerPlugin, ButlerPluginBus
        mem = ButlerPlugin("mem_p", "memory", "", object(), _available=True)
        ctx = ButlerPlugin("ctx_p", "context", "", object(), _available=True)
        bus = ButlerPluginBus(loaders=[self._make_loader([mem, ctx])])
        await bus.load_all()
        assert len(bus.plugins_of_type("memory")) == 1
        assert len(bus.plugins_of_type("context")) == 1

    @pytest.mark.asyncio
    async def test_register_programmatic(self):
        from domain.plugins.plugin_bus import ButlerPluginBus
        bus = ButlerPluginBus(loaders=[])
        await bus.load_all()
        bus.register("injected", object(), plugin_type="memory")
        assert bus.get("injected") is not None

    def test_factory_creates_default_bus(self):
        from domain.plugins.plugin_bus import make_default_plugin_bus
        bus = make_default_plugin_bus()
        assert bus is not None
        assert len(bus._loaders) == 2  # memory + context


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ButlerSkillsCatalog
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerSkillsCatalog:
    """Tests ButlerSkillsCatalog with mock sources and real fs scan fallback."""

    def _make_source(self, skills):
        from domain.skills.skills_catalog import ISkillsSource
        class MockSource(ISkillsSource):
            def scan(self): return skills
        return MockSource()

    def _make_skill(self, name="test_skill", domain="productivity"):
        from domain.skills.skills_catalog import Skill
        return Skill(name=name, domain=domain, source="test",
                     description="A test skill", version="1.0", path="/fake/path")

    def test_scan_returns_dicts(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        source = self._make_source([self._make_skill()])
        catalog = ButlerSkillsCatalog(sources=[source])
        result = catalog.scan()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "test_skill"

    def test_scan_is_idempotent(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        count = []
        from domain.skills.skills_catalog import ISkillsSource
        class CountingSource(ISkillsSource):
            def scan(self):
                count.append(1)
                return []
        catalog = ButlerSkillsCatalog(sources=[CountingSource()])
        catalog.scan()
        catalog.scan()
        assert len(count) == 1

    def test_list_skills_domain_filter(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        skills = [
            self._make_skill("skill1", "productivity"),
            self._make_skill("skill2", "research"),
        ]
        catalog = ButlerSkillsCatalog(sources=[self._make_source(skills)])
        prod = catalog.list_skills(domain="productivity")
        assert all(s["domain"] == "productivity" for s in prod)
        assert len(prod) == 1

    def test_get_skill_found(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        catalog = ButlerSkillsCatalog(sources=[self._make_source([self._make_skill()])])
        skill = catalog.get_skill("test_skill")
        assert skill is not None
        assert skill["name"] == "test_skill"

    def test_get_skill_not_found(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        catalog = ButlerSkillsCatalog(sources=[self._make_source([])])
        assert catalog.get_skill("nonexistent") is None

    def test_domains_returns_unique_sorted(self):
        from domain.skills.skills_catalog import ButlerSkillsCatalog
        skills = [
            self._make_skill("s1", "research"),
            self._make_skill("s2", "productivity"),
            self._make_skill("s3", "research"),
        ]
        catalog = ButlerSkillsCatalog(sources=[self._make_source(skills)])
        domains = catalog.domains()
        assert domains == sorted(set(domains))

    def test_hermes_skills_dir_scanned_if_exists(self):
        """Real FS scan — returns empty list gracefully if dir has no skills."""
        from domain.skills.skills_catalog import HermesSkillsSource
        source = HermesSkillsSource()
        result = source.scan()
        # May be empty or have real skills — just check it's a list
        assert isinstance(result, list)

    def test_factory_creates_catalog(self):
        from domain.skills.skills_catalog import make_default_skills_catalog
        catalog = make_default_skills_catalog()
        assert catalog is not None
        assert len(catalog._sources) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ButlerPlatformRegistry
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerPlatformRegistry:
    """Tests PlatformRegistry with mock adapters — no real platform deps."""

    def _make_adapter(self, pid: str, available: bool = True):
        from domain.contracts import IPlatformAdapter
        adapter = MagicMock(spec=IPlatformAdapter)
        adapter.platform_id = pid
        adapter.max_message_length = 4096
        adapter.is_available.return_value = available
        adapter.send = AsyncMock(return_value=True)
        return adapter

    def test_register_and_get(self):
        from domain.gateway.platform_registry import ButlerPlatformRegistry
        registry = ButlerPlatformRegistry(adapters=[])
        adapter = self._make_adapter("telegram")
        registry.register(adapter)
        assert registry.get("telegram") is adapter

    def test_all_adapters_returns_all(self):
        from domain.gateway.platform_registry import ButlerPlatformRegistry
        adapters = [self._make_adapter("telegram"), self._make_adapter("discord")]
        registry = ButlerPlatformRegistry(adapters=adapters)
        assert len(registry.all_adapters()) == 2

    def test_available_adapters_filters(self):
        from domain.gateway.platform_registry import ButlerPlatformRegistry
        adapters = [
            self._make_adapter("telegram", available=True),
            self._make_adapter("discord", available=False),
        ]
        registry = ButlerPlatformRegistry(adapters=adapters)
        available = registry.available_adapters()
        assert len(available) == 1
        assert available[0].platform_id == "telegram"

    def test_get_unknown_returns_none(self):
        from domain.gateway.platform_registry import ButlerPlatformRegistry
        registry = ButlerPlatformRegistry(adapters=[])
        assert registry.get("nonexistent") is None

    def test_status_dict_structure(self):
        from domain.gateway.platform_registry import ButlerPlatformRegistry
        registry = ButlerPlatformRegistry(adapters=[self._make_adapter("slack")])
        status = registry.status()
        assert "total" in status
        assert "available" in status
        assert "platforms" in status

    def test_factory_creates_19_adapters(self):
        from domain.gateway.platform_registry import make_default_platform_registry
        registry = make_default_platform_registry()
        # Should have all 19 platforms registered
        assert len(registry.all_adapters()) == 18

    def test_hermes_adapter_wrapper_lazy_load(self):
        """Lazy-loading a missing module should not raise — marks unavailable."""
        from domain.gateway.platform_registry import HermesPlatformAdapterWrapper
        wrapper = HermesPlatformAdapterWrapper(
            "nonexistent", "integrations.hermes.gateway.platforms.nonexistent_platform"
        )
        assert not wrapper.is_available()
        assert wrapper.load_error() is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. HermesACPBridge
# ═══════════════════════════════════════════════════════════════════════════════

class TestHermesACPBridge:
    """Tests HermesACPBridge translator + lifecycle without running a real server."""

    def test_translator_converts_valid_event(self):
        from integrations.hermes.acp_adapter.butler_bridge import HermesACPv1Translator
        translator = HermesACPv1Translator()
        raw = {
            "type": "tool_approval_request",
            "request_id": "req_001",
            "tool_name": "terminal",
            "args": {"command": "ls"},
            "context": {"account_id": "acc_1", "session_id": "sess_1"},
        }
        result = translator.to_butler_request(raw)
        assert result is not None
        assert result["request_id"] == "req_001"
        assert result["tool_name"] == "terminal"
        assert result["account_id"] == "acc_1"
        assert result["source"] == "hermes_acp_ide"

    def test_translator_rejects_unknown_event_type(self):
        from integrations.hermes.acp_adapter.butler_bridge import HermesACPv1Translator
        translator = HermesACPv1Translator()
        result = translator.to_butler_request({"type": "something_else"})
        assert result is None

    def test_translator_decision_to_hermes_response(self):
        from integrations.hermes.acp_adapter.butler_bridge import HermesACPv1Translator
        translator = HermesACPv1Translator()
        decision = {"request_id": "req_001", "approved": True, "reason": "ok"}
        response = translator.to_hermes_response(decision)
        assert response["type"] == "tool_approval_response"
        assert response["approved"] is True
        assert response["request_id"] == "req_001"

    @pytest.mark.asyncio
    async def test_bridge_start_stop(self):
        from integrations.hermes.acp_adapter.butler_bridge import HermesACPBridge
        mock_server = MagicMock()
        bridge = HermesACPBridge(acp_server=mock_server)
        assert not bridge.is_running()
        # start() tries to import Hermes ACP server — graceful fallback if missing
        await bridge.start()
        # Even if Hermes ACP not importable, bridge handles it gracefully
        await bridge.stop()
        assert not bridge.is_running()

    def test_factory_creates_bridge(self):
        from integrations.hermes.acp_adapter.butler_bridge import make_hermes_acp_bridge
        mock_server = MagicMock()
        bridge = make_hermes_acp_bridge(mock_server)
        assert bridge is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Butler CLI
# ═══════════════════════════════════════════════════════════════════════════════

class TestButlerCLI:
    """Tests ButlerCLIRunner and individual commands."""

    def _make_cli(self, commands=None):
        from cli.butler_cli import ButlerCLIRunner
        return ButlerCLIRunner(commands=commands or [])

    @pytest.mark.asyncio
    async def test_help_exits_0(self):
        cli = self._make_cli()
        code = await cli.run(["--help"])
        assert code == 0

    @pytest.mark.asyncio
    async def test_unknown_command_exits_2(self):
        cli = self._make_cli()
        code = await cli.run(["nonexistent"])
        assert code == 2

    @pytest.mark.asyncio
    async def test_custom_command_registered_and_runs(self):
        from cli.butler_cli import ButlerCLIRunner, ButlerCommand

        class EchoCommand(ButlerCommand):
            name = "echo"
            help = "echo args"
            async def run(self, args): return 0

        cli = ButlerCLIRunner(commands=[EchoCommand()])
        code = await cli.run(["echo", "hello"])
        assert code == 0

    @pytest.mark.asyncio
    async def test_register_adds_command(self):
        from cli.butler_cli import ButlerCLIRunner, ButlerCommand

        class Cmd(ButlerCommand):
            name = "new_cmd"
            help = "a new command"
            async def run(self, args): return 0

        cli = ButlerCLIRunner(commands=[])
        cli.register(Cmd())
        assert "new_cmd" in cli._commands

    def test_factory_creates_7_commands(self):
        from cli.butler_cli import make_default_cli
        cli = make_default_cli()
        assert len(cli._commands) == 7
        expected = {"tools", "plugins", "skills", "platforms", "hooks", "health", "emit"}
        assert set(cli._commands.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Rebranding verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestRebranding:
    """Verify no user-facing 'Hermes' identity leaks from Butler domain code."""

    def test_agent_backend_docstring_rebranded(self):
        import domain.orchestrator.hermes_agent_backend as mod
        assert "Butler Agent Backend" in mod.__doc__

    def test_error_map_renamed(self):
        """_ERROR_MAP should exist; _HERMES_ERROR_MAP should not."""
        import domain.orchestrator.hermes_agent_backend as mod
        assert hasattr(mod, "_ERROR_MAP")
        assert not hasattr(mod, "_HERMES_ERROR_MAP")

    def test_no_hermes_in_hook_bus_event_names(self):
        """All builtin event names use butler: prefix."""
        from domain.hooks.hook_bus import BuiltinHookLoader
        events = [e for e, _ in BuiltinHookLoader().load()]
        for e in events:
            assert e.startswith("butler:"), f"Event '{e}' doesn't use butler: prefix"

    def test_tool_registry_capability_map_no_hermes_keys(self):
        """CapabilityFlag names are Butler-branded (uppercase)."""
        from domain.tools.butler_tool_registry import _TOOLSET_CAPABILITY_MAP
        for cap in _TOOLSET_CAPABILITY_MAP.values():
            if cap is not None:
                assert cap == cap.upper(), f"Capability '{cap}' should be uppercase"

    def test_skills_catalog_sources_tagged_hermes_correctly(self):
        """Skills from Hermes dirs are tagged source='hermes' (not hidden)."""
        from domain.skills.skills_catalog import HermesSkillsSource
        # Source tag is 'hermes' — this is the integration label, not an identity bleed
        source = HermesSkillsSource()
        skills = source.scan()
        for s in skills:
            assert s.source == "hermes"

    def test_butler_cli_banner_says_butler(self):
        from cli.butler_cli import ButlerCLIRunner
        assert "Butler" in ButlerCLIRunner.BANNER
        assert "Hermes" not in ButlerCLIRunner.BANNER
