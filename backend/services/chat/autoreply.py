from __future__ import annotations
import re
from typing import Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class CommandType(str, Enum):
    DIRECT = "direct"
    ARG = "arg"
    PATTERN = "pattern"
    SUBAGENT = "subagent"


@dataclass
class Command:
    name: str
    description: str
    pattern: str
    command_type: CommandType = CommandType.DIRECT
    handler: Callable | None = None
    aliases: list[str] = field(default_factory=list)
    permission: str = "user"


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._patterns: list[tuple[re.Pattern, Command]] = []
    
    def register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd
        if cmd.command_type == CommandType.PATTERN:
            self._patterns.append((re.compile(cmd.pattern), cmd))
    
    def find(self, text: str) -> Command | None:
        parts = text.strip().split()
        if not parts:
            return None
        first = parts[0].lower()
        if first in self._commands:
            return self._commands[first]
        for pattern, cmd in self._patterns:
            if pattern.match(text):
                return cmd
        return None
    
    def list_commands(self) -> list[dict[str, str]]:
        return [{"name": c.name, "description": c.description} for c in self._commands.values()]


class ExecutionResult:
    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str | None = None,
        actions: list[dict[str, Any]] = field(default_factory=list),
    ):
        self.success = success
        self.output = output
        self.error = error
        self.actions = actions
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "actions": self.actions,
        }


class CommandExecutor:
    def __init__(self, registry: CommandRegistry):
        self._registry = registry
    
    async def execute(self, text: str, context: dict[str, Any]) -> ExecutionResult:
        cmd = self._registry.find(text)
        if not cmd:
            return ExecutionResult(False, error="Unknown command")
        
        if cmd.handler is None:
            return ExecutionResult(True, output=f"Command {cmd.name} registered")
        
        try:
            result = cmd.handler(text, context)
            return ExecutionResult(True, output=str(result))
        except Exception as e:
            return ExecutionResult(False, error=str(e))


class SubAgent:
    def __init__(self, name: str, prompt: str, model: str = "anthropic"):
        self.name = name
        self.prompt = prompt
        self.model = model
        self._active = False
    
    async def run(self, input_text: str, context: dict[str, Any]) -> str:
        return f"[{self.name}] Processing: {input_text}"


class SubAgentPool:
    def __init__(self):
        self._subagents: dict[str, SubAgent] = {}
    
    def register(self, agent: SubAgent) -> None:
        self._subagents[agent.name] = agent
    
    def get(self, name: str) -> SubAgent | None:
        return self._subagents.get(name)
    
    def list(self) -> list[str]:
        return list(self._subagents.keys())


class MessageQueue:
    def __init__(self, max_size: int = 100):
        self._queue: list[dict[str, Any]] = []
        self._max_size = max_size
    
    def enqueue(self, message: dict[str, Any]) -> bool:
        if len(self._queue) >= self._max_size:
            return False
        self._queue.append(message)
        return True
    
    def dequeue(self) -> dict[str, Any] | None:
        if not self._queue:
            return None
        return self._queue.pop(0)
    
    def peek(self) -> dict[str, Any] | None:
        return self._queue[0] if self._queue else None
    
    def size(self) -> int:
        return len(self._queue)
    
    def clear(self) -> None:
        self._queue.clear()


class AutoReplySystem:
    def __init__(self):
        self.commands = CommandRegistry()
        self.subagents = SubAgentPool()
        self.queue = MessageQueue()
        self.executor = CommandExecutor(self.commands)
        self._setup_default_commands()
    
    def _setup_default_commands(self) -> None:
        self.commands.register(Command(
            name="help",
            description="Show available commands",
            pattern=r"^help",
            handler=lambda text, ctx: "\n".join(
                f"{c.name}: {c.description}" for c in self.commands.list_commands()
            ),
        ))
        self.commands.register(Command(
            name="status",
            description="System status",
            pattern=r"^status",
            handler=lambda text, ctx: f"Queue: {self.queue.size()}, Subagents: {len(self.subagents.list())}",
        ))
        self.commands.register(Command(
            name="clear",
            description="Clear message queue",
            pattern=r"^clear",
            handler=lambda text, ctx: (self.queue.clear(), "Queue cleared")[1],
        ))
    
    async def process(self, text: str, context: dict[str, Any]) -> ExecutionResult:
        cmd = self.commands.find(text)
        if not cmd:
            return ExecutionResult(False, error="No matching command")
        return await self.executor.execute(text, context)