from enum import Enum, StrEnum


class CapabilityArea(StrEnum):
    """The 18 canonical capability areas of the Butler system."""

    WEB_SEARCH = "web_search"
    SEARCH_ENGINE = "search_engine"
    MESSAGING = "messaging"
    SOCIAL_PRESENCE = "social_presence"
    CALENDAR_OPS = "calendar_ops"
    MEETING_ASSISTANT = "meeting_assistant"
    MEMORY_OPS = "memory_ops"
    DATA_ANALYSIS = "data_analysis"
    IOT_CONTROL = "iot_control"
    VISION_REASONING = "vision_reasoning"
    AUDIO_FLOW = "audio_flow"
    DELEGATION = "delegation"
    PLATFORM_PLUGINS = "platform_plugins"
    SYSTEM_OPS = "system_ops"
    FINANCE_GATEWAY = "finance_gateway"
    HEALTH_INTEGRATION = "health_integration"
    STREAMS_MGMT = "streams_mgmt"
    GEN_AI_FACTORY = "gen_ai_factory"


class TrustLevel(int, Enum):
    """Trust levels for inputs and subagents."""

    INTERNAL = 0  # Butler heartbeats, kernel tasks
    VERIFIED_USER = 1  # Direct user commands
    PEER_AGENT = 2  # ACP-verified subagents
    UNTRUSTED = 3  # Web research, unknown MCP tools


class SubagentIsolationClass(StrEnum):
    """The 5-class matrix for subagent runtime isolation."""

    IN_PROCESS = "in_process"  # Shared memory, same Python interpreter
    PROCESS_POOL = "process_pool"  # Isolated Unix process, limited IPC
    SANDBOX = "sandbox"  # gVisor/Wasm container, net isolation
    REMOTE_PEER = "remote_peer"  # External ACP node, no shared state
    HUMAN_GATE = "human_gate"  # Human-in-the-loop task routing
