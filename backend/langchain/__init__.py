"""
Butler LangChain Integration Module

Butler owns governance (RiskTier, ToolExecutor, audit).
LangChain provides power (adapters, state, checkpointing, tools, memory).

Version: 2.0.0 - Full LangGraph Integration
"""

__version__ = "2.0.0"

# Core Components
from .evaluator import ButlerEvaluator, EvaluationResult
from .memory import ButlerMemoryAdapter
from .models import ButlerChatModel, ChatModelFactory
from .retrievers import ButlerSearchRetriever
from .tools import ButlerLangChainTool, ButlerToolFactory
from .agent import ButlerAgentBuilder, ButlerAgentState, create_agent

# Middleware
from .middleware.base import ButlerBaseMiddleware, MiddlewareResult, ButlerMiddlewareContext
from .middleware.cost_tracking import ButlerCostTrackingMiddleware
from .middleware.content_guard import ButlerContentGuardMiddleware
from .middleware.tool_retry import ButlerToolRetryMiddleware
from .middleware.caching import ButlerCachingMiddleware
from .middleware.registry import ButlerMiddlewareRegistry
from .middleware.hitl import ButlerHITLMiddleware, ApprovalStrategy, ApprovalStatus, ApprovalRequest

# Time Travel
from .time_travel import ButlerTimeTravel, CheckpointState

# Structured Output
from .structured_output import ButlerStructuredOutput, ToolCall, AgentResponse

# Protocols
from .protocols.mcp import ButlerMCPTool, ButlerMCPServer, MCPResource, MCPPrompt
from .protocols.a2a import ButlerA2AClient, ButlerA2AServer, AgentMessage, AgentCapability, MessageType, Priority
from .protocols.acp import ButlerACPClient, ButlerACPServer, ACPMessage, ACPCapability, ACPAction, ACPStatus

# Multi-Agent
from .multi_agent import ButlerMultiAgentOrchestrator, ButlerDeepAgent, ButlerAgentHierarchy, AgentRole, AgentConfig

# Observability
from .observability import ButlerAgentTracer, ButlerAgentMetrics, ButlerAgentEvaluator, ButlerObservability, AgentSpan, AgentMetric

# Server & Runtime
from .server import ButlerAgentServer, ButlerAgentRuntime

# Auth & Identity
from .auth import ButlerAuthContext, ButlerConnectionManager, ButlerAuthMiddleware, ButlerAgentAuth, ButlerIdentity, ButlerConnection

# UI & Functional API
from .ui import ButlerGenerativeUI, ButlerFunctionalAPI, ButlerUIAPI, UIComponent, UIEvent, FunctionalAPICall

# Deployment
from .deployment import ButlerDeploymentManager, ButlerHealthChecker, ButlerDeploymentOrchestrator, ButlerDeploymentInfra, DeploymentConfig, HealthCheck

# Integrations
from .integrations_catalog import ButlerIntegrationsCatalog, Integration, IntegrationConfig, IntegrationType, IntegrationStatus

# Prompts
from .prompts import ButlerPromptLibrary, ButlerPromptOptimizer, ButlerPromptEngine, PromptTemplate, PromptOptimization

# Compliance & Privacy
from .compliance import ButlerComplianceChecker, ButlerPrivacyController, ButlerAuditLogger, ButlerCompliancePrivacy, ComplianceRule, AuditLogEntry, ComplianceLevel, PrivacyLevel, ComplianceCheck

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
