"""Butler Backend CLI — Phase 11.

A backend operator CLI rebranded from Hermes's rich interactive shell.
Gives platform operators direct access to Butler's internals:
  - Tool discovery and test execution
  - Plugin status
  - Skills browser
  - Session history search
  - Platform adapter status
  - Hook bus inspection
  - Health probe readout

NOT shipped to end users — this is an operator / developer tool.
Launched via: python -m cli.butler_cli or butler-cli (entry point).

Architecture (SOLID):
  S — each command class handles exactly one concern
  O — new commands extend ButlerCommand without modifying CLI runner
  L — all commands satisfy ButlerCommand protocol
  I — ButlerCommand is a tiny interface (name, help, run)
  D — runner depends on ButlerCommand list — injected / auto-discovered
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# Graceful fallback if rich is not installed
try:
    from rich import print as rprint
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    RICH = True
except ImportError:
    RICH = False
    Console = None  # type: ignore[misc,assignment]

import structlog

logger = structlog.get_logger(__name__)


# ── ButlerCommand protocol (I — tiny interface) ───────────────────────────────

class ButlerCommand:
    """Base class for all Butler CLI commands.

    Single responsibility: one command per subclass (S).
    New commands extend without modifying the runner (O).
    All substitutable via this base (L).
    """

    name: str = ""
    help: str = ""

    async def run(self, args: list[str]) -> int:
        """Execute the command. Returns exit code (0 = success)."""
        raise NotImplementedError


# ── Concrete commands (S — each one thing) ────────────────────────────────────

class ToolsCommand(ButlerCommand):
    """Show all registered Butler tools grouped by toolset."""

    name = "tools"
    help = "List all registered Butler tools (grouped by toolset)"

    async def run(self, args: list[str]) -> int:
        from domain.tools.butler_tool_registry import make_default_tool_registry
        registry = make_default_tool_registry()
        discovered = registry.discover()

        if RICH:
            c = Console()
            c.print(Panel("[bold cyan]Butler Tool Registry[/bold cyan]", expand=False))
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Tool", style="cyan", min_width=30)
            table.add_column("Toolset")
            table.add_column("Capability Gate")
            for name, toolset in sorted(registry.get_toolset_map().items()):
                cap = registry.get_capability_for_tool(name) or "—"
                table.add_row(name, toolset, cap)
            c.print(table)
            c.print(f"\n[green]{len(discovered)} modules discovered[/green]")
        else:
            for name, toolset in sorted(registry.get_toolset_map().items()):
                print(f"{name:<35} {toolset:<20} {registry.get_capability_for_tool(name) or '—'}")
        return 0


class PluginsCommand(ButlerCommand):
    """Show loaded plugin status."""

    name = "plugins"
    help = "Show Butler plugin bus status"

    async def run(self, args: list[str]) -> int:
        from domain.plugins.plugin_bus import make_default_plugin_bus
        bus = make_default_plugin_bus()
        await bus.load_all()
        status = bus.status()

        if RICH:
            c = Console()
            c.print(Panel("[bold cyan]Butler Plugin Bus[/bold cyan]", expand=False))
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Plugin")
            table.add_column("Type")
            table.add_column("Available")
            table.add_column("Error")
            for p in status["plugins"]:
                avail = "[green]✓[/green]" if p["available"] else "[red]✗[/red]"
                table.add_row(p["name"], p["type"], avail, p.get("error") or "")
            c.print(table)
            c.print(f"\n[bold]{status['available']}/{status['total']} plugins available[/bold]")
        else:
            for p in status["plugins"]:
                print(f"{p['name']:<25} {p['type']:<12} {'OK' if p['available'] else 'FAIL'}")
        return 0


class SkillsCommand(ButlerCommand):
    """Browse the Butler skills catalog."""

    name = "skills"
    help = "Browse the Butler × Hermes skills catalog"

    async def run(self, args: list[str]) -> int:
        domain_filter = args[0] if args else None
        from domain.skills.skills_catalog import make_default_skills_catalog
        catalog = make_default_skills_catalog()
        skills = catalog.list_skills(domain=domain_filter)

        if RICH:
            c = Console()
            title = f"Butler Skills — domain: {domain_filter}" if domain_filter else "Butler Skills Catalog"
            c.print(Panel(f"[bold cyan]{title}[/bold cyan]", expand=False))
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Name", min_width=25)
            table.add_column("Domain")
            table.add_column("Source")
            table.add_column("Description")
            for s in skills:
                table.add_row(s["name"], s["domain"], s["source"], s["description"][:60])
            c.print(table)
            c.print(f"\n[green]{len(skills)} skills found[/green]")
        else:
            for s in skills:
                print(f"{s['name']:<28} {s['domain']:<18} {s['source']}")

        # Show domains if no filter
        if not domain_filter:
            domains = catalog.domains()
            if RICH:
                Console().print(f"[dim]Domains: {', '.join(domains)}[/dim]")
            else:
                print(f"Domains: {', '.join(domains)}")
        return 0


class PlatformsCommand(ButlerCommand):
    """Show platform adapter statuses."""

    name = "platforms"
    help = "Show all 19 Butler platform adapter statuses"

    async def run(self, args: list[str]) -> int:
        from domain.gateway.platform_registry import make_default_platform_registry
        registry = make_default_platform_registry()
        status = registry.status()

        if RICH:
            c = Console()
            c.print(Panel("[bold cyan]Butler Platform Registry[/bold cyan]", expand=False))
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Platform", min_width=16)
            table.add_column("Available")
            table.add_column("Max Msg Length")
            for p in status["platforms"]:
                avail = "[green]✓[/green]" if p["available"] else "[dim]—[/dim]"
                table.add_row(p["id"], avail, str(p["max_len"]))
            c.print(table)
            c.print(f"\n[bold]{status['available']}/{status['total']} platforms available[/bold]")
        else:
            for p in status["platforms"]:
                print(f"{p['id']:<18} {'OK' if p['available'] else '—':<6} {p['max_len']}")
        return 0


class HooksCommand(ButlerCommand):
    """Show loaded lifecycle hooks."""

    name = "hooks"
    help = "List all loaded Butler lifecycle event hooks"

    async def run(self, args: list[str]) -> int:
        from domain.hooks.hook_bus import make_default_hook_bus
        bus = make_default_hook_bus()
        bus.load()

        if RICH:
            c = Console()
            c.print(Panel("[bold cyan]Butler Hook Bus[/bold cyan]", expand=False))
            events = bus.event_names()
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Event Type", min_width=30)
            table.add_column("Handler Count")
            for event in events:
                table.add_row(event, str(len(bus._handlers.get(event, []))))
            c.print(table)
            c.print(f"\n[green]{len(events)} event types registered[/green]")
        else:
            for event in bus.event_names():
                count = len(bus._handlers.get(event, []))
                print(f"{event:<35} {count} handler(s)")
        return 0


class HealthCommand(ButlerCommand):
    """Run the Butler health probe."""

    name = "health"
    help = "Run Butler health probes (live/ready/startup)"

    async def run(self, args: list[str]) -> int:
        import httpx
        probe = args[0] if args else "ready"
        url = f"http://localhost:8000/health/{probe}"
        try:
            r = httpx.get(url, timeout=5.0)
            data = r.json()
            if RICH:
                c = Console()
                colour = "green" if r.status_code == 200 else "red"
                c.print(Panel(
                    f"[{colour}]{json.dumps(data, indent=2)}[/{colour}]",
                    title=f"[bold]Health /{probe}[/bold]",
                ))
            else:
                print(json.dumps(data, indent=2))
            return 0 if r.status_code == 200 else 1
        except Exception as exc:
            print(f"Health check failed: {exc}", file=sys.stderr)
            return 1


class EmitCommand(ButlerCommand):
    """Emit a Butler lifecycle event for testing hooks."""

    name = "emit"
    help = "Emit a butler: lifecycle event (for testing hooks). Usage: emit <event>"

    async def run(self, args: list[str]) -> int:
        if not args:
            print("Usage: butler-cli emit <event> [key=value ...]", file=sys.stderr)
            return 1
        event = args[0]
        ctx: dict[str, Any] = {}
        for kv in args[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                ctx[k] = v

        from domain.hooks.hook_bus import make_default_hook_bus
        bus = make_default_hook_bus()
        bus.load()
        await bus.emit(event, ctx)
        if RICH:
            Console().print(f"[green]✓[/green] Emitted [bold]{event}[/bold] with context: {ctx}")
        else:
            print(f"Emitted {event} with {ctx}")
        return 0


# ── CLI Runner (D — depends on ButlerCommand list, injected) ──────────────────

class ButlerCLIRunner:
    """Lightweight CLI runner.

    Depends on ButlerCommand list — injected (D).
    New commands added via register() without touching the runner (O).
    """

    BANNER = """
╔══════════════════════════════════════════╗
║       Butler CLI — Operator Tools        ║
║  AI Sovereignty Infrastructure v11       ║
╚══════════════════════════════════════════╝
"""

    def __init__(self, commands: list[ButlerCommand]) -> None:
        self._commands: dict[str, ButlerCommand] = {c.name: c for c in commands}

    def register(self, command: ButlerCommand) -> None:
        self._commands[command.name] = command

    async def run(self, argv: list[str]) -> int:
        if not argv or argv[0] in ("-h", "--help", "help"):
            self._print_help()
            return 0

        cmd_name = argv[0]
        cmd = self._commands.get(cmd_name)
        if cmd is None:
            print(f"Unknown command: {cmd_name}", file=sys.stderr)
            self._print_help()
            return 2

        return await cmd.run(argv[1:])

    def _print_help(self) -> None:
        if RICH:
            c = Console()
            c.print(Panel(self.BANNER.strip(), style="bold blue"))
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Command")
            table.add_column("Description")
            for name, cmd in sorted(self._commands.items()):
                table.add_row(f"[cyan]{name}[/cyan]", cmd.help)
            c.print(table)
        else:
            print(self.BANNER)
            for name, cmd in sorted(self._commands.items()):
                print(f"  {name:<15} {cmd.help}")


# ── Default factory ───────────────────────────────────────────────────────────

def make_default_cli() -> ButlerCLIRunner:
    """Production CLI with all built-in commands registered."""
    return ButlerCLIRunner(commands=[
        ToolsCommand(),
        PluginsCommand(),
        SkillsCommand(),
        PlatformsCommand(),
        HooksCommand(),
        HealthCommand(),
        EmitCommand(),
    ])


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    cli = make_default_cli()
    exit_code = asyncio.run(cli.run(sys.argv[1:]))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
