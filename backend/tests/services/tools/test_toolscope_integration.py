"""Tests for ToolScope integration with Butler tool system.

Tests semantic tool retrieval, policy filtering, and observability.
"""

from __future__ import annotations

import pytest
from domain.tools.specs import ButlerToolSpec, RiskTier, ApprovalMode, ExecutableKind


class TestButlerEmbedderAdapter:
    """Test Butler embedder adapter for ToolScope."""

    def test_adapter_initialization(self):
        """Test adapter can be initialized with EmbeddingService."""
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        assert adapter._embedding_service is not None

    def test_adapter_embed_texts(self):
        """Test adapter embed_texts method."""
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        texts = ["get current time", "search web", "send email"]
        embeddings = adapter.embed_texts(texts)

        assert len(embeddings) == 3
        assert all(isinstance(emb, list) for emb in embeddings)
        assert all(len(emb) > 0 for emb in embeddings)


class TestToolScopeService:
    """Test ToolScope service integration."""

    @pytest.fixture
    def sample_tools(self):
        """Create sample Butler tool specs for testing."""
        return [
            ButlerToolSpec(
                name="get_time",
                version="1.0.0",
                description="Get the current date and time for a given timezone",
                owner="tools",
                risk_tier=RiskTier.L0,
                approval_mode=ApprovalMode.NONE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "default": "UTC"},
                    },
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                    },
                },
                executable_kind=ExecutableKind.DIRECT_FUNCTION,
                binding_ref="get_time",
                timeout_ms=5000,
                idempotent=True,
                enabled=True,
                model_visible=True,
                tags=["time", "deterministic"],
            ),
            ButlerToolSpec(
                name="web_search",
                version="1.0.0",
                description="Search the web for information",
                owner="tools",
                risk_tier=RiskTier.L1,
                approval_mode=ApprovalMode.NONE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "results": {"type": "array"},
                    },
                },
                executable_kind=ExecutableKind.DIRECT_FUNCTION,
                binding_ref="web_search",
                timeout_ms=10000,
                idempotent=True,
                enabled=True,
                model_visible=True,
                tags=["web", "search"],
            ),
            ButlerToolSpec(
                name="send_email",
                version="1.0.0",
                description="Send an email to a recipient",
                owner="tools",
                risk_tier=RiskTier.L2,
                approval_mode=ApprovalMode.OPTIONAL,
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                    },
                },
                executable_kind=ExecutableKind.DIRECT_FUNCTION,
                binding_ref="send_email",
                timeout_ms=30000,
                idempotent=False,
                enabled=True,
                model_visible=True,
                tags=["email", "communication"],
            ),
        ]

    def test_service_initialization(self):
        """Test ToolScope service can be initialized."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=5, max_risk_tier="L2")
        assert service._k == 5
        assert service._max_risk_tier == "L2"
        assert service._enable_reranking is False
        assert service._enable_sticky_sessions is True

    def test_build_index(self, sample_tools):
        """Test building ToolScope index from Butler specs."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=2)
        service.build_index(sample_tools)
        assert service._index is not None

    def test_filter_tools_by_query(self, sample_tools):
        """Test filtering tools by user query."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=2)
        service.build_index(sample_tools)

        # Query for time-related tools
        filtered_tools, trace = service.filter_tools(
            messages="What time is it?",
            max_risk_tier="L2",
        )

        assert len(filtered_tools) <= 2
        assert isinstance(trace, dict)
        assert "final_tool_count" in trace

    def test_filter_tools_with_risk_tier_filter(self, sample_tools):
        """Test filtering tools respects risk tier limits."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=10)
        service.build_index(sample_tools)

        # Filter to only L0 and L1 tools
        filtered_tools, trace = service.filter_tools(
            messages="search and get time",
            max_risk_tier="L1",
        )

        # Should not include L2 tools like send_email
        tool_names = [spec.name for spec in filtered_tools]
        assert "send_email" not in tool_names
        assert trace["final_tool_count"] == len(filtered_tools)

    def test_filter_tools_with_permissions(self, sample_tools):
        """Test filtering tools respects permission requirements."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        # Add a tool with required permissions
        sample_tools.append(
            ButlerToolSpec(
                name="admin_delete",
                version="1.0.0",
                description="Delete administrative records",
                owner="admin",
                risk_tier=RiskTier.L3,
                approval_mode=ApprovalMode.REQUIRED,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                executable_kind=ExecutableKind.DIRECT_FUNCTION,
                binding_ref="admin_delete",
                timeout_ms=5000,
                idempotent=False,
                enabled=True,
                model_visible=True,
                tags=["admin", "delete"],
            )
        )

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=10)
        service.build_index(sample_tools)

        # Filter with limited permissions
        filtered_tools, trace = service.filter_tools(
            messages="delete records",
            account_permissions=frozenset(["read_only"]),
            max_risk_tier="L3",
        )

        # Should filter out tools requiring admin permissions
        tool_names = [spec.name for spec in filtered_tools]
        assert "admin_delete" not in tool_names

    def test_filter_tools_observability_trace(self, sample_tools):
        """Test filtering returns detailed trace metadata."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=2)
        service.build_index(sample_tools)

        filtered_tools, trace = service.filter_tools(
            messages="get current time",
            max_risk_tier="L2",
        )

        # Check trace metadata
        assert "final_tool_count" in trace
        assert "final_tool_names" in trace
        assert "butler_policy_filtered" in trace
        assert isinstance(trace["butler_policy_filtered"], list)

    def test_filter_tools_without_index(self):
        """Test filtering returns empty when index not built."""
        from services.tools.toolscope_service import ToolScopeService
        from services.tools.toolscope_service import ButlerEmbedderAdapter
        from services.ml.embeddings import EmbeddingService

        embedding_service = EmbeddingService()
        adapter = ButlerEmbedderAdapter(embedding_service)
        service = ToolScopeService(embedding_adapter=adapter, k=2)
        filtered_tools, trace = service.filter_tools(messages="test")

        assert len(filtered_tools) == 0
        assert trace.get("error") == "index_not_built"


class TestToolScopeOrchestratorIntegration:
    """Test ToolScope integration with execution orchestrator."""

    def test_orchestrator_initializes_toolscope_service(self):
        """Test orchestrator can initialize ToolScope service."""
        from services.orchestrator.execution_orchestrator import ExecutionOrchestrator

        orchestrator = ExecutionOrchestrator()
        # ToolScope service is lazy loaded, so it should be None initially
        assert orchestrator._toolscope_service is None

    def test_orchestrator_has_toolscope_attribute(self):
        """Test orchestrator has ToolScope service attribute."""
        from services.orchestrator.execution_orchestrator import ExecutionOrchestrator

        orchestrator = ExecutionOrchestrator()
        assert hasattr(orchestrator, "_toolscope_service")


class TestToolScopeConfiguration:
    """Test ToolScope configuration integration."""

    def test_settings_has_toolscope_config(self):
        """Test settings include ToolScope configuration."""
        from infrastructure.config import settings

        assert hasattr(settings, "TOOLSCOPE_ENABLED")
        assert hasattr(settings, "TOOLSCOPE_K")
        assert hasattr(settings, "TOOLSCOPE_ENABLE_RERANKING")
        assert hasattr(settings, "TOOLSCOPE_ENABLE_STICKY_SESSIONS")
        assert hasattr(settings, "TOOLSCOPE_MAX_RISK_TIER")
        assert hasattr(settings, "TOOLSCOPE_TOOL_TEXT_TRUNCATE")

    def test_settings_default_values(self):
        """Test ToolScope settings have sensible defaults."""
        from infrastructure.config import settings

        assert settings.TOOLSCOPE_ENABLED is True
        assert settings.TOOLSCOPE_K == 8
        assert settings.TOOLSCOPE_ENABLE_RERANKING is False
        assert settings.TOOLSCOPE_ENABLE_STICKY_SESSIONS is True
        assert settings.TOOLSCOPE_MAX_RISK_TIER == "L2"
        assert settings.TOOLSCOPE_TOOL_TEXT_TRUNCATE == 256


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
