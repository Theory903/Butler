"""Tests for CrewAI Phase 2 integration with Butler.

This module tests the Phase 2 CrewAI integration features:
- Flow control integration with Butler's Durable Workflow
- Conditional routing using CrewAI's @router decorator
- Checkpoint/resume with CrewAI state management
- Knowledge/RAG integration
"""

import pytest
from pydantic import BaseModel

from services.crewai.config import CrewAIConfig
from services.crewai.flow_integration import ButlerCheckpointHandler, CrewAIFlowAdapter
from services.crewai.conditional_routing import (
    ButlerRouterAdapter,
    ConditionalFlowBuilder,
    butler_approval_policy_check,
    butler_resource_policy_check,
)
from services.crewai.knowledge_integration import CrewAIKnowledgeAdapter, HybridKnowledgeRetriever


class MockContext(BaseModel):
    """Mock context for testing."""

    user_message: str
    requires_approval: bool = False
    estimated_cost: int = 100


def test_crewai_flow_adapter_initialization():
    """Test CrewAI Flow adapter initialization."""
    config = CrewAIConfig()
    adapter = CrewAIFlowAdapter(config=config)

    assert adapter._config == config
    assert adapter._content_guard is None


def test_butler_checkpoint_handler_initialization():
    """Test Butler checkpoint handler initialization."""
    handler = ButlerCheckpointHandler()

    assert handler._db_session is None


@pytest.mark.asyncio
async def test_butler_checkpoint_handler_save_and_load():
    """Test Butler checkpoint handler save and load."""
    handler = ButlerCheckpointHandler()

    flow_state = {"inputs": {"test": "data"}, "outputs": "test result"}
    checkpoint_id = await handler.save_checkpoint(flow_state, metadata={"test": True})

    assert checkpoint_id is not None
    assert checkpoint_id.startswith("crewai_checkpoint_")

    loaded_state = await handler.load_checkpoint(checkpoint_id)
    # Phase 2: Returns None (placeholder)
    # Phase 3: Will return actual state
    assert loaded_state is None


def test_butler_router_adapter_initialization():
    """Test Butler Router adapter initialization."""
    config = CrewAIConfig()
    adapter = ButlerRouterAdapter(config=config)

    assert adapter._config == config
    assert adapter._content_guard is None
    assert len(adapter._router_functions) == 0


def test_butler_router_adapter_register_function():
    """Test registering router function."""
    adapter = ButlerRouterAdapter()

    async def test_router(context):
        return "test_route"

    adapter.register_router_function("test", test_router)

    assert "test" in adapter._router_functions
    assert adapter._router_functions["test"] == test_router


@pytest.mark.asyncio
async def test_butler_approval_policy_check():
    """Test Butler approval policy check."""
    context = MockContext(
        user_message="test", requires_approval=False, estimated_cost=100
    )
    result = await butler_approval_policy_check(context=context)

    assert result.get("allowed") is True

    context_with_approval = MockContext(
        user_message="test", requires_approval=True, estimated_cost=100
    )
    result = await butler_approval_policy_check(context=context_with_approval)

    assert result.get("allowed") is False
    assert "approval" in result.get("reason", "").lower()


@pytest.mark.asyncio
async def test_butler_resource_policy_check():
    """Test Butler resource policy check."""
    context = MockContext(
        user_message="test", requires_approval=False, estimated_cost=100
    )
    result = await butler_resource_policy_check(context=context)

    assert result.get("allowed") is True

    context_high_cost = MockContext(
        user_message="test", requires_approval=False, estimated_cost=2000
    )
    result = await butler_resource_policy_check(context=context_high_cost)

    assert result.get("allowed") is False
    assert "cost" in result.get("reason", "").lower()


def test_conditional_flow_builder_initialization():
    """Test Conditional Flow Builder initialization."""
    config = CrewAIConfig()
    builder = ConditionalFlowBuilder(config=config)

    assert builder._config == config
    assert len(builder._conditions) == 0


def test_conditional_flow_builder_add_condition():
    """Test adding condition to Conditional Flow Builder."""
    builder = ConditionalFlowBuilder()

    async def test_condition(context):
        return context.get("test_value") == True

    builder.add_condition("test_condition", test_condition, "test_route")

    assert len(builder._conditions) == 1
    assert builder._conditions[0]["name"] == "test_condition"
    assert builder._conditions[0]["target_route"] == "test_route"


def test_conditional_flow_builder_build_router():
    """Test building router from conditions."""
    builder = ConditionalFlowBuilder()

    async def condition1(context):
        return context.get("value") == 1

    async def condition2(context):
        return context.get("value") == 2

    builder.add_condition("cond1", condition1, "route1")
    builder.add_condition("cond2", condition2, "route2")

    router = builder.build_crewai_router()

    assert router is not None


@pytest.mark.asyncio
async def test_conditional_flow_builder_router_execution():
    """Test executing router built from conditions."""
    builder = ConditionalFlowBuilder()

    async def condition1(context):
        return context.get("value") == 1

    async def condition2(context):
        return context.get("value") == 2

    builder.add_condition("cond1", condition1, "route1")
    builder.add_condition("cond2", condition2, "route2")

    router = builder.build_crewai_router()

    # Test matching first condition
    result = await router({"value": 1})
    assert result == "route1"

    # Test matching second condition
    result = await router({"value": 2})
    assert result == "route2"

    # Test fallback to default
    result = await router({"value": 3})
    assert result == "default"


def test_crewai_knowledge_adapter_initialization():
    """Test CrewAI Knowledge adapter initialization."""
    config = CrewAIConfig()
    adapter = CrewAIKnowledgeAdapter(config=config)

    assert adapter._config == config
    assert adapter._content_guard is None
    assert adapter._vector_store is None


def test_crewai_knowledge_adapter_set_vector_store():
    """Test setting vector store in Knowledge adapter."""
    adapter = CrewAIKnowledgeAdapter()

    mock_vector_store = {"test": "vector_store"}
    adapter.set_vector_store(mock_vector_store)

    assert adapter._vector_store == mock_vector_store


@pytest.mark.asyncio
async def test_crewai_knowledge_adapter_ingest_document():
    """Test document ingestion (requires CrewAI installation)."""
    adapter = CrewAIKnowledgeAdapter()

    # This will fail without CrewAI installed, which is expected
    result = await adapter.ingest_document(
        document_path="test.pdf",
        document_type="pdf",
        metadata={"test": True},
    )

    # Without CrewAI, should return error
    assert result.get("success") is False
    assert "CrewAI not installed" in result.get("error", "")


@pytest.mark.asyncio
async def test_crewai_knowledge_adapter_retrieve_knowledge():
    """Test knowledge retrieval (requires CrewAI installation)."""
    adapter = CrewAIKnowledgeAdapter()

    # This will fail without CrewAI installed, which is expected
    result = await adapter.retrieve_knowledge(query="test query", top_k=5)

    # Without CrewAI, should return empty list
    assert result == []


def test_hybrid_knowledge_retriever_initialization():
    """Test Hybrid Knowledge Retriever initialization."""
    crewai_adapter = CrewAIKnowledgeAdapter()
    retriever = HybridKnowledgeRetriever(crewai_adapter=crewai_adapter)

    assert retriever._crewai_adapter == crewai_adapter


@pytest.mark.asyncio
async def test_hybrid_knowledge_retriever_retrieve():
    """Test hybrid knowledge retrieval."""
    crewai_adapter = CrewAIKnowledgeAdapter()
    retriever = HybridKnowledgeRetriever(crewai_adapter=crewai_adapter)

    result = await retriever.retrieve(query="test query", top_k=5, sources=["both"])

    assert "crewai" in result
    assert "butler" in result
    assert "merged" in result


@pytest.mark.asyncio
async def test_butler_router_adapter_execute_conditional_routing():
    """Test executing conditional routing through Butler Router adapter."""
    adapter = ButlerRouterAdapter()

    async def test_router(context):
        return f"route_for_{context.get('value')}"

    adapter.register_router_function("test", test_router)

    result = await adapter.execute_conditional_routing(
        context={"value": "test"},
        router_name="test",
    )

    assert result.get("route") == "route_for_test"
    assert result.get("router_name") == "test"


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        # Run basic tests without CrewAI installation
        test_crewai_flow_adapter_initialization()
        test_butler_checkpoint_handler_initialization()
        await test_butler_checkpoint_handler_save_and_load()
        test_butler_router_adapter_initialization()
        test_butler_router_adapter_register_function()
        await test_butler_approval_policy_check()
        await test_butler_resource_policy_check()
        test_conditional_flow_builder_initialization()
        test_conditional_flow_builder_add_condition()
        test_conditional_flow_builder_build_router()
        await test_conditional_flow_builder_router_execution()
        test_crewai_knowledge_adapter_initialization()
        test_crewai_knowledge_adapter_set_vector_store()
        await test_crewai_knowledge_adapter_ingest_document()
        await test_crewai_knowledge_adapter_retrieve_knowledge()
        test_hybrid_knowledge_retriever_initialization()
        await test_hybrid_knowledge_retriever_retrieve()
        await test_butler_router_adapter_execute_conditional_routing()

        print("All Phase 2 basic tests passed!")

    asyncio.run(run_tests())
