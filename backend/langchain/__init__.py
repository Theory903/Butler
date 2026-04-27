"""
Butler LangChain Integration Module

Butler owns governance (RiskTier, ToolExecutor, audit).
LangChain provides power (adapters, state, checkpointing, tools, memory).

Version: 2.0.0 - Full LangGraph Integration
"""

__version__ = "2.0.0"

# Core Components
from .agent import ButlerAgentBuilder, ButlerAgentState, create_agent

# Auth & Identity
from .auth import (
    ButlerAgentAuth,
    ButlerAuthContext,
    ButlerAuthMiddleware,
    ButlerConnection,
    ButlerConnectionManager,
    ButlerIdentity,
)

# Compliance & Privacy
from .compliance import (
    AuditLogEntry,
    ButlerAuditLogger,
    ButlerComplianceChecker,
    ButlerCompliancePrivacy,
    ButlerPrivacyController,
    ComplianceCheck,
    ComplianceLevel,
    ComplianceRule,
    PrivacyLevel,
)

# Deployment
from .deployment import (
    ButlerDeploymentInfra,
    ButlerDeploymentManager,
    ButlerDeploymentOrchestrator,
    ButlerHealthChecker,
    DeploymentConfig,
    HealthCheck,
)
from .evaluator import ButlerEvaluator, EvaluationResult

# Integrations
from .integrations_catalog import (
    ButlerIntegrationsCatalog,
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)
from .memory import ButlerMemoryAdapter

# Middleware
from .middleware.base import ButlerBaseMiddleware, ButlerMiddlewareContext, MiddlewareResult
from .middleware.caching import ButlerCachingMiddleware
from .middleware.content_guard import ButlerContentGuardMiddleware
from .middleware.cost_tracking import ButlerCostTrackingMiddleware
from .middleware.hitl import ApprovalRequest, ApprovalStatus, ApprovalStrategy, ButlerHITLMiddleware
from .middleware.registry import ButlerMiddlewareRegistry
from .middleware.tool_retry import ButlerToolRetryMiddleware
from .models import ButlerChatModel, ChatModelFactory

# Multi-Agent
from .multi_agent import (
    AgentConfig,
    AgentRole,
    ButlerAgentHierarchy,
    ButlerDeepAgent,
    ButlerMultiAgentOrchestrator,
)

# Observability
from .observability import (
    AgentMetric,
    AgentSpan,
    ButlerAgentEvaluator,
    ButlerAgentMetrics,
    ButlerAgentTracer,
    ButlerObservability,
)

# Prompts
from .prompts import (
    ButlerPromptEngine,
    ButlerPromptLibrary,
    ButlerPromptOptimizer,
    PromptOptimization,
    PromptTemplate,
)
from .protocols.a2a import (
    AgentCapability,
    AgentMessage,
    ButlerA2AClient,
    ButlerA2AServer,
    MessageType,
    Priority,
)
from .protocols.acp import (
    ACPAction,
    ACPCapability,
    ACPMessage,
    ACPStatus,
    ButlerACPClient,
    ButlerACPServer,
)

# Protocols
from .protocols.mcp import ButlerMCPServer, ButlerMCPTool, MCPPrompt, MCPResource
from .retrievers import ButlerSearchRetriever

# Server & Runtime
from .server import ButlerAgentRuntime, ButlerAgentServer

# Structured Output
from .structured_output import AgentResponse, ButlerStructuredOutput, ToolCall

# Time Travel
from .time_travel import ButlerTimeTravel, CheckpointState
from .tools import ButlerLangChainTool, ButlerToolFactory

# UI & Functional API
from .ui import (
    ButlerFunctionalAPI,
    ButlerGenerativeUI,
    ButlerUIAPI,
    FunctionalAPICall,
    UIComponent,
    UIEvent,
)

__all__ = [
    # Core Components
    "ButlerEvaluator",
    "EvaluationResult",
    "ButlerMemoryAdapter",
    "ButlerChatModel",
    "ChatModelFactory",
    "ButlerSearchRetriever",
    "ButlerLangChainTool",
    "ButlerToolFactory",
    "ButlerAgentBuilder",
    "ButlerAgentState",
    "create_agent",
    # Middleware
    "ButlerBaseMiddleware",
    "MiddlewareResult",
    "ButlerMiddlewareContext",
    "ButlerCostTrackingMiddleware",
    "ButlerContentGuardMiddleware",
    "ButlerToolRetryMiddleware",
    "ButlerCachingMiddleware",
    "ButlerMiddlewareRegistry",
    "ButlerHITLMiddleware",
    "ApprovalStrategy",
    "ApprovalStatus",
    "ApprovalRequest",
    # Time Travel
    "ButlerTimeTravel",
    "CheckpointState",
    # Structured Output
    "ButlerStructuredOutput",
    "ToolCall",
    "AgentResponse",
    # Protocols
    "ButlerMCPTool",
    "ButlerMCPServer",
    "MCPResource",
    "MCPPrompt",
    "ButlerA2AClient",
    "ButlerA2AServer",
    "AgentMessage",
    "AgentCapability",
    "MessageType",
    "Priority",
    "ButlerACPClient",
    "ButlerACPServer",
    "ACPMessage",
    "ACPCapability",
    "ACPAction",
    "ACPStatus",
    # Multi-Agent
    "ButlerMultiAgentOrchestrator",
    "ButlerDeepAgent",
    "ButlerAgentHierarchy",
    "AgentRole",
    "AgentConfig",
    # Observability
    "ButlerAgentTracer",
    "ButlerAgentMetrics",
    "ButlerAgentEvaluator",
    "ButlerObservability",
    "AgentSpan",
    "AgentMetric",
    # Server & Runtime
    "ButlerAgentServer",
    "ButlerAgentRuntime",
    # Auth & Identity
    "ButlerAuthContext",
    "ButlerConnectionManager",
    "ButlerAuthMiddleware",
    "ButlerAgentAuth",
    "ButlerIdentity",
    "ButlerConnection",
    # UI & Functional API
    "ButlerGenerativeUI",
    "ButlerFunctionalAPI",
    "ButlerUIAPI",
    "UIComponent",
    "UIEvent",
    "FunctionalAPICall",
    # Deployment
    "ButlerDeploymentManager",
    "ButlerHealthChecker",
    "ButlerDeploymentOrchestrator",
    "ButlerDeploymentInfra",
    "DeploymentConfig",
    "HealthCheck",
    # Integrations
    "ButlerIntegrationsCatalog",
    "Integration",
    "IntegrationConfig",
    "IntegrationType",
    "IntegrationStatus",
    # Prompts
    "ButlerPromptLibrary",
    "ButlerPromptOptimizer",
    "ButlerPromptEngine",
    "PromptTemplate",
    "PromptOptimization",
    # Compliance & Privacy
    "ButlerComplianceChecker",
    "ButlerPrivacyController",
    "ButlerAuditLogger",
    "ButlerCompliancePrivacy",
    "ComplianceRule",
    "AuditLogEntry",
    "ComplianceLevel",
    "PrivacyLevel",
    "ComplianceCheck",
]
