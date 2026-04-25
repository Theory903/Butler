"""Tests for Phase 3: Memory + HITL + Time Travel + Structured Output."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain.memory import ButlerMemoryAdapter
from langchain.middleware.hitl import (
    ButlerHITLMiddleware,
    ApprovalStrategy,
    ApprovalStatus,
    ApprovalRequest,
)
from langchain.time_travel import ButlerTimeTravel, CheckpointState
from langchain.structured_output import (
    ButlerStructuredOutput,
    ToolCall,
    AgentResponse,
)
from domain.memory.contracts import MemoryServiceContract


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service."""
    service = MagicMock(spec=MemoryServiceContract)
    service.build_context = AsyncMock()
    service.store_turn = AsyncMock()
    return service


@pytest.fixture
def memory_adapter(mock_memory_service):
    """Create a ButlerMemoryAdapter instance."""
    return ButlerMemoryAdapter(
        session_id="test_session",
        account_id="test_account",
        memory_service=mock_memory_service,
    )


class TestButlerMemoryAdapter:
    """Tests for ButlerMemoryAdapter."""

    @pytest.mark.asyncio
    async def test_memory_adapter_initialization(self, memory_adapter):
        """Test that memory adapter initializes correctly."""
        assert memory_adapter.session_id == "test_session"
        assert memory_adapter.account_id == "test_account"
        assert memory_adapter.memory_service is not None

    @pytest.mark.asyncio
    async def test_memory_adapter_store_turn(self, memory_adapter, mock_memory_service):
        """Test storing a turn in memory."""
        from langchain_core.messages import HumanMessage

        message = HumanMessage(content="test message")
        await memory_adapter.aadd_messages([message])

        mock_memory_service.store_turn.assert_called_once_with(
            account_id="test_account",
            session_id="test_session",
            role="user",
            content="test message",
        )

    @pytest.mark.asyncio
    async def test_memory_adapter_retrieve_context(self, memory_adapter, mock_memory_service):
        """Test retrieving context from memory."""
        from domain.memory.contracts import ContextPack
        from domain.memory.models import ConversationTurn

        # Mock context pack
        mock_context = ContextPack(
            session_history=[
                ConversationTurn(role="user", content="test", session_id="test_session", account_id="test_account_id")
            ],
            relevant_memories=[],
            preferences=[],
            entities=[],
            summary_anchor="Test summary",
            context_token_budget=1000,
        )
        mock_memory_service.build_context.return_value = mock_context

        messages = await memory_adapter.aget_messages()

        assert len(messages) > 0
        mock_memory_service.build_context.assert_called_once()


class TestButlerHITLMiddleware:
    """Tests for ButlerHITLMiddleware."""

    def test_hitl_middleware_initialization(self):
        """Test HITL middleware initialization."""
        middleware = ButlerHITLMiddleware(
            enabled=True,
            strategy=ApprovalStrategy.MANUAL,
        )
        assert middleware.enabled is True
        assert middleware._strategy == ApprovalStrategy.MANUAL

    def test_hitl_approval_request_creation(self):
        """Test approval request creation."""
        request = ApprovalRequest(
            request_id="test_id",
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            operation_type="tool_call",
            operation_details={"tool_name": "email_sender"},
        )
        assert request.status == ApprovalStatus.PENDING

    def test_hitl_approve_request(self):
        """Test approving a request."""
        request = ApprovalRequest(
            request_id="test_id",
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            operation_type="tool_call",
            operation_details={"tool_name": "email_sender"},
        )
        request.approve()
        assert request.status == ApprovalStatus.APPROVED

    def test_hitl_deny_request(self):
        """Test denying a request."""
        request = ApprovalRequest(
            request_id="test_id",
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            operation_type="tool_call",
            operation_details={"tool_name": "email_sender"},
        )
        request.deny()
        assert request.status == ApprovalStatus.DENIED

    @pytest.mark.asyncio
    async def test_hitl_auto_approve_strategy(self):
        """Test auto-approve strategy."""
        from langchain.middleware.base import ButlerMiddlewareContext

        middleware = ButlerHITLMiddleware(
            enabled=True,
            strategy=ApprovalStrategy.AUTO_APPROVE,
            require_tool_approval=True,
        )

        context = ButlerMiddlewareContext(
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            model="gpt-4",
            messages=[],
            tool_calls=[{"name": "email_sender", "args": {"to": "test@example.com"}}],
        )

        result = await middleware.pre_tool(context)

        assert result.success is True
        assert result.should_continue is True

    @pytest.mark.asyncio
    async def test_hitl_auto_deny_strategy(self):
        """Test auto-deny strategy."""
        from langchain.middleware.base import ButlerMiddlewareContext

        middleware = ButlerHITLMiddleware(
            enabled=True,
            strategy=ApprovalStrategy.AUTO_DENY,
            require_tool_approval=True,
        )

        context = ButlerMiddlewareContext(
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            model="gpt-4",
            messages=[],
            tool_calls=[{"name": "email_sender", "args": {"to": "test@example.com"}}],
        )

        result = await middleware.pre_tool(context)

        assert result.success is False
        assert result.should_continue is False

    @pytest.mark.asyncio
    async def test_hitl_manual_approval_required(self):
        """Test manual approval requirement."""
        from langchain.middleware.base import ButlerMiddlewareContext

        middleware = ButlerHITLMiddleware(
            enabled=True,
            strategy=ApprovalStrategy.MANUAL,
            require_tool_approval=True,
        )

        context = ButlerMiddlewareContext(
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            model="gpt-4",
            messages=[],
            tool_calls=[{"name": "email_sender", "args": {"to": "test@example.com"}}],
        )

        result = await middleware.pre_tool(context)

        assert result.success is False
        assert result.should_continue is False
        assert result.error and "Approval required" in result.error


class TestButlerTimeTravel:
    """Tests for ButlerTimeTravel."""

    def test_time_travel_initialization(self):
        """Test time travel service initialization."""
        compiled_graph = MagicMock()
        checkpointer = MagicMock()
        
        time_travel = ButlerTimeTravel(compiled_graph, checkpointer)
        
        assert time_travel._compiled_graph == compiled_graph
        assert time_travel._checkpointer == checkpointer

    def test_checkpoint_state_creation(self):
        """Test checkpoint state creation."""
        from datetime import datetime, timezone
        
        state = CheckpointState(
            checkpoint_id="cp_1",
            thread_id="thread_1",
            timestamp=datetime.now(timezone.utc),
            state={"messages": []},
            parent_checkpoint_id=None,
        )
        assert state.checkpoint_id == "cp_1"
        assert state.thread_id == "thread_1"

    @pytest.mark.asyncio
    async def test_get_checkpoint_history(self):
        """Test getting checkpoint history."""
        compiled_graph = MagicMock()
        checkpointer = MagicMock()
        
        # Mock asearch to return empty iterator
        checkpointer.asearch = AsyncMock(return_value=iter([]))
        
        time_travel = ButlerTimeTravel(compiled_graph, checkpointer)
        
        history = await time_travel.get_checkpoint_history("thread_1", limit=10)
        
        assert isinstance(history, list)
        checkpointer.asearch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_checkpoint(self):
        """Test getting a specific checkpoint."""
        compiled_graph = MagicMock()
        checkpointer = MagicMock()
        
        # Mock aget to return None
        checkpointer.aget = AsyncMock(return_value=None)
        
        time_travel = ButlerTimeTravel(compiled_graph, checkpointer)
        
        checkpoint = await time_travel.get_checkpoint("thread_1", "cp_1")
        
        assert checkpoint is None
        checkpointer.aget.assert_called_once()


class TestButlerStructuredOutput:
    """Tests for ButlerStructuredOutput."""

    def test_structured_output_initialization(self):
        """Test structured output initialization."""
        chat_model = MagicMock()
        structured_output = ButlerStructuredOutput(chat_model)
        
        assert structured_output._chat_model == chat_model

    def test_tool_call_schema(self):
        """Test ToolCall schema."""
        tool_call = ToolCall(
            tool_name="email_sender",
            arguments={"to": "test@example.com"},
            reasoning="Send email to user",
        )
        assert tool_call.tool_name == "email_sender"
        assert tool_call.arguments["to"] == "test@example.com"

    def test_agent_response_schema(self):
        """Test AgentResponse schema."""
        response = AgentResponse(
            content="Hello world",
            confidence=0.95,
        )
        assert response.content == "Hello world"
        assert response.confidence == 0.95

    def test_create_tool_from_schema(self):
        """Test creating tool definition from schema."""
        chat_model = MagicMock()
        structured_output = ButlerStructuredOutput(chat_model)
        
        tool_def = structured_output.create_tool_from_schema(
            schema=ToolCall,
            name="email_sender",
            description="Send an email",
        )
        
        assert tool_def["type"] == "function"
        assert tool_def["function"]["name"] == "email_sender"
        assert "parameters" in tool_def["function"]

    def test_validate_output_with_pydantic(self):
        """Test validating output with Pydantic schema."""
        chat_model = MagicMock()
        structured_output = ButlerStructuredOutput(chat_model)
        
        output = '{"tool_name": "email_sender", "arguments": {"to": "test@example.com"}}'
        
        validated = structured_output.validate_output(output, ToolCall)
        
        assert isinstance(validated, ToolCall)
        assert validated.tool_name == "email_sender"

    def test_validate_output_invalid_json(self):
        """Test validating output with invalid JSON."""
        chat_model = MagicMock()
        structured_output = ButlerStructuredOutput(chat_model)
        
        output = "invalid json"
        
        # Should return original output on failure
        validated = structured_output.validate_output(output, ToolCall)
        
        assert validated == output


class TestPhase3Integration:
    """Integration tests for Phase 3 components."""

    @pytest.mark.asyncio
    async def test_memory_with_agent_flow(self, memory_adapter, mock_memory_service):
        """Test memory integration with agent flow."""
        from domain.memory.contracts import ContextPack
        from domain.memory.models import ConversationTurn
        from langchain_core.messages import HumanMessage

        # Mock context retrieval
        mock_context = ContextPack(
            session_history=[
                ConversationTurn(role="user", content="previous message", session_id="test_session", account_id="test_account_id")
            ],
            relevant_memories=[],
            preferences=[],
            entities=[],
            summary_anchor="Previous conversation summary",
            context_token_budget=1000,
        )
        mock_memory_service.build_context.return_value = mock_context

        # Store a new message
        await memory_adapter.aadd_messages([HumanMessage(content="new message")])

        # Retrieve context
        messages = await memory_adapter.aget_messages()

        # Verify both operations were called
        mock_memory_service.store_turn.assert_called()
        mock_memory_service.build_context.assert_called()

    @pytest.mark.asyncio
    async def test_hitl_with_sensitive_tool(self):
        """Test HITL middleware with sensitive tool."""
        from langchain.middleware.base import ButlerMiddlewareContext

        middleware = ButlerHITLMiddleware(
            enabled=True,
            strategy=ApprovalStrategy.MANUAL,
            require_tool_approval=True,
        )

        context = ButlerMiddlewareContext(
            tenant_id="tenant_1",
            account_id="account_1",
            session_id="session_1",
            trace_id="trace_1",
            model="gpt-4",
            messages=[],
            tool_calls=[{"name": "payment_processor", "args": {"amount": 100}}],
        )

        result = await middleware.pre_tool(context)

        assert result.success is False
        assert result.should_continue is False
        assert len(middleware.get_pending_approvals()) == 1

    def test_structured_output_validation_chain(self):
        """Test structured output validation chain."""
        chat_model = MagicMock()
        structured_output = ButlerStructuredOutput(chat_model)

        # Validate output
        output = '{"content": "Response", "tool_calls": [], "confidence": 0.9}'
        validated = structured_output.validate_output(output, AgentResponse)

        assert isinstance(validated, AgentResponse)
        assert validated.content == "Response"
