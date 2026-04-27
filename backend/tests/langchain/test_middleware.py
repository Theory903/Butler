"""Tests for Butler LangChain Middleware."""

import pytest

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareOrder,
    MiddlewareResult,
)
from langchain.middleware.registry import ButlerMiddlewareRegistry


class DummyMiddleware(ButlerBaseMiddleware):
    """Dummy middleware for testing."""

    def __init__(self, enabled: bool = True, should_block: bool = False):
        super().__init__(enabled=enabled)
        self.should_block = should_block
        self.pre_model_called = False
        self.post_model_called = False
        self.pre_tool_called = False
        self.post_tool_called = False

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        self.pre_model_called = True
        if self.should_block:
            return MiddlewareResult(success=False, should_continue=False, error="Blocked by dummy")
        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        self.post_model_called = True
        return MiddlewareResult(success=True, should_continue=True)

    async def pre_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        self.pre_tool_called = True
        return MiddlewareResult(success=True, should_continue=True)

    async def post_tool(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        self.post_tool_called = True
        return MiddlewareResult(success=True, should_continue=True)


@pytest.fixture
def middleware_context():
    """Create a test middleware context."""
    return ButlerMiddlewareContext(
        tenant_id="test_tenant",
        account_id="test_account",
        session_id="test_session",
        trace_id="test_trace",
        user_id="test_user",
        model="gpt-4",
        tier="T2",
        messages=[{"role": "user", "content": "test message"}],
    )


class TestButlerBaseMiddleware:
    """Tests for ButlerBaseMiddleware."""

    @pytest.mark.asyncio
    async def test_middleware_enabled(self, middleware_context):
        """Test that enabled middleware processes."""
        middleware = DummyMiddleware(enabled=True)
        result = await middleware.process(middleware_context, MiddlewareOrder.PRE_MODEL)
        assert result.success is True
        assert result.should_continue is True
        assert middleware.pre_model_called is True

    @pytest.mark.asyncio
    async def test_middleware_disabled(self, middleware_context):
        """Test that disabled middleware skips processing."""
        middleware = DummyMiddleware(enabled=False)
        result = await middleware.process(middleware_context, MiddlewareOrder.PRE_MODEL)
        assert result.success is True
        assert result.should_continue is True
        assert middleware.pre_model_called is False

    @pytest.mark.asyncio
    async def test_middleware_blocking(self, middleware_context):
        """Test that blocking middleware short-circuits."""
        middleware = DummyMiddleware(enabled=True, should_block=True)
        result = await middleware.process(middleware_context, MiddlewareOrder.PRE_MODEL)
        assert result.success is False
        assert result.should_continue is False
        assert result.error == "Blocked by dummy"

    @pytest.mark.asyncio
    async def test_middleware_routing(self, middleware_context):
        """Test that middleware routes to correct hooks."""
        middleware = DummyMiddleware(enabled=True)
        await middleware.process(middleware_context, MiddlewareOrder.PRE_MODEL)
        await middleware.process(middleware_context, MiddlewareOrder.POST_MODEL)
        await middleware.process(middleware_context, MiddlewareOrder.PRE_TOOL)
        await middleware.process(middleware_context, MiddlewareOrder.POST_TOOL)

        assert middleware.pre_model_called is True
        assert middleware.post_model_called is True
        assert middleware.pre_tool_called is True
        assert middleware.post_tool_called is True


class TestButlerMiddlewareRegistry:
    """Tests for ButlerMiddlewareRegistry."""

    def test_register_middleware(self):
        """Test registering middleware."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        result = registry.register(middleware, MiddlewareOrder.PRE_MODEL, order=1)
        assert result is registry

    def test_register_pre_model(self):
        """Test registering PRE_MODEL middleware."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        registry.register_pre_model(middleware, order=1)
        middleware_list = registry.get_middleware_for_hook(MiddlewareOrder.PRE_MODEL)
        assert middleware in middleware_list

    def test_register_post_model(self):
        """Test registering POST_MODEL middleware."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        registry.register_post_model(middleware, order=1)
        middleware_list = registry.get_middleware_for_hook(MiddlewareOrder.POST_MODEL)
        assert middleware in middleware_list

    def test_register_pre_tool(self):
        """Test registering PRE_TOOL middleware."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        registry.register_pre_tool(middleware, order=1)
        middleware_list = registry.get_middleware_for_hook(MiddlewareOrder.PRE_TOOL)
        assert middleware in middleware_list

    def test_register_post_tool(self):
        """Test registering POST_TOOL middleware."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        registry.register_post_tool(middleware, order=1)
        middleware_list = registry.get_middleware_for_hook(MiddlewareOrder.POST_TOOL)
        assert middleware in middleware_list

    @pytest.mark.asyncio
    async def test_execute_middleware_pipeline(self, middleware_context):
        """Test executing middleware pipeline."""
        registry = ButlerMiddlewareRegistry()
        middleware1 = DummyMiddleware()
        middleware2 = DummyMiddleware()

        registry.register_pre_model(middleware1, order=1)
        registry.register_pre_model(middleware2, order=2)

        result = await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)

        assert result.success is True
        assert result.should_continue is True
        assert middleware1.pre_model_called is True
        assert middleware2.pre_model_called is True

    @pytest.mark.asyncio
    async def test_execute_middleware_ordering(self, middleware_context):
        """Test that middleware executes in order."""
        registry = ButlerMiddlewareRegistry()
        middleware1 = DummyMiddleware()
        middleware2 = DummyMiddleware()

        registry.register_pre_model(middleware1, order=2)
        registry.register_pre_model(middleware2, order=1)

        await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)

        # middleware2 should be called first (order 1)
        # middleware1 should be called second (order 2)
        assert middleware2.pre_model_called is True
        assert middleware1.pre_model_called is True

    @pytest.mark.asyncio
    async def test_execute_middleware_short_circuit(self, middleware_context):
        """Test that middleware short-circuits on block."""
        registry = ButlerMiddlewareRegistry()
        middleware1 = DummyMiddleware()
        middleware2 = DummyMiddleware(should_block=True)
        middleware3 = DummyMiddleware()

        registry.register_pre_model(middleware1, order=1)
        registry.register_pre_model(middleware2, order=2)
        registry.register_pre_model(middleware3, order=3)

        result = await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)

        assert result.success is False
        assert result.should_continue is False
        assert middleware1.pre_model_called is True
        assert middleware2.pre_model_called is True
        assert middleware3.pre_model_called is False

    def test_clear_registry(self):
        """Test clearing the registry."""
        registry = ButlerMiddlewareRegistry()
        middleware = DummyMiddleware()

        registry.register_pre_model(middleware, order=1)
        assert len(registry.get_middleware_for_hook(MiddlewareOrder.PRE_MODEL)) == 1

        registry.clear()
        assert len(registry.get_middleware_for_hook(MiddlewareOrder.PRE_MODEL)) == 0


class TestComposedMiddlewarePipeline:
    """Tests for composed middleware pipelines."""

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, middleware_context):
        """Test executing a full middleware pipeline."""
        registry = ButlerMiddlewareRegistry()

        pre_middleware = DummyMiddleware()
        post_middleware = DummyMiddleware()
        pre_tool_middleware = DummyMiddleware()
        post_tool_middleware = DummyMiddleware()

        registry.register_pre_model(pre_middleware, order=1)
        registry.register_post_model(post_middleware, order=1)
        registry.register_pre_tool(pre_tool_middleware, order=1)
        registry.register_post_tool(post_tool_middleware, order=1)

        await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)
        await registry.execute(middleware_context, MiddlewareOrder.POST_MODEL)
        await registry.execute(middleware_context, MiddlewareOrder.PRE_TOOL)
        await registry.execute(middleware_context, MiddlewareOrder.POST_TOOL)

        assert pre_middleware.pre_model_called is True
        assert post_middleware.post_model_called is True
        assert pre_tool_middleware.pre_tool_called is True
        assert post_tool_middleware.post_tool_called is True

    @pytest.mark.asyncio
    async def test_middleware_modification_propagation(self, middleware_context):
        """Test that middleware modifications propagate through the pipeline."""
        registry = ButlerMiddlewareRegistry()

        class ModifyingMiddleware(ButlerBaseMiddleware):
            def __init__(self):
                super().__init__(enabled=True)

            async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
                context.messages.append({"role": "system", "content": "modified"})
                return MiddlewareResult(
                    success=True,
                    should_continue=True,
                    modified_input={"messages": context.messages},
                )

        middleware = ModifyingMiddleware()
        registry.register_pre_model(middleware, order=1)

        initial_count = len(middleware_context.messages)
        result = await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)

        assert result.success is True
        assert len(middleware_context.messages) == initial_count + 1

    @pytest.mark.asyncio
    async def test_middleware_metadata_aggregation(self, middleware_context):
        """Test that middleware metadata is aggregated."""
        registry = ButlerMiddlewareRegistry()

        class MetadataMiddleware(ButlerBaseMiddleware):
            def __init__(self, key: str, value: str):
                super().__init__(enabled=True)
                self.key = key
                self.value = value

            async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
                return MiddlewareResult(
                    success=True,
                    should_continue=True,
                    metadata={self.key: self.value},
                )

        middleware1 = MetadataMiddleware("key1", "value1")
        middleware2 = MetadataMiddleware("key2", "value2")

        registry.register_pre_model(middleware1, order=1)
        registry.register_pre_model(middleware2, order=2)

        result = await registry.execute(middleware_context, MiddlewareOrder.PRE_MODEL)

        assert result.metadata.get("key1") == "value1"
        assert result.metadata.get("key2") == "value2"
