"""Tests for CrewAI integration with Butler.

This module tests the CrewAI multi-agent collaboration integration
within Butler's execution framework.
"""

import pytest
import uuid
from pydantic import BaseModel

from domain.runtime.execution_class import ExecutionClass
from domain.runtime.envelope import ButlerRuntimeEnvelope, UserInput
from services.crewai.config import (
    CrewAIConfig,
    CrewAgentConfig,
    DomainRequirement,
)
from services.crewai.builder import CrewAIBuilder
from services.orchestrator.execution_orchestrator import ExecutionOrchestrator


class MockIntentResult(BaseModel):
    """Mock intent result for testing."""

    execution_class: ExecutionClass
    intent: str
    metadata: dict


def test_crewai_config():
    """Test CrewAI configuration."""
    config = CrewAIConfig(
        model="openai/gpt-4o",
        temperature=0.7,
        max_tokens=4000,
    )

    assert config.model == "openai/gpt-4o"
    assert config.temperature == 0.7
    assert config.max_tokens == 4000
    assert config.enable_security_guardrails is True
    assert config.enable_memory_integration is True


def test_crew_agent_config():
    """Test CrewAI agent configuration."""
    agent_config = CrewAgentConfig(
        role="Research Specialist",
        goal="Conduct comprehensive research",
        backstory="An expert researcher with years of experience",
    )

    assert agent_config.role == "Research Specialist"
    assert agent_config.goal == "Conduct comprehensive research"
    assert agent_config.safety_class == "safe_auto"
    assert agent_config.requires_approval is False


def test_domain_requirement():
    """Test domain requirement configuration."""
    domain_req = DomainRequirement(
        domain="research",
        complexity="medium",
        agent_roles=["researcher", "analyst", "writer"],
    )

    assert domain_req.domain == "research"
    assert domain_req.complexity == "medium"
    assert domain_req.requires_multi_agent is True
    assert len(domain_req.agent_roles) == 3


def test_crewai_builder_initialization():
    """Test CrewAI builder initialization."""
    config = CrewAIConfig()
    builder = CrewAIBuilder(config=config)

    assert builder._config == config
    assert builder._llm is not None


def test_crewai_builder_get_default_roles():
    """Test getting default roles for a domain."""
    builder = CrewAIBuilder()

    research_roles = builder._get_default_roles("research")
    assert "researcher" in research_roles
    assert "analyst" in research_roles
    assert "writer" in research_roles

    financial_roles = builder._get_default_roles("financial_analysis")
    assert "financial_analyst" in financial_roles
    assert "risk_assessor" in financial_roles

    general_roles = builder._get_default_roles("unknown")
    assert general_roles == ["generalist"]


def test_crewai_builder_get_agent_config():
    """Test getting agent configuration for a role."""
    builder = CrewAIBuilder()
    agent_config = builder._get_agent_config("researcher", "research")

    assert agent_config.role == "Researcher"
    assert "research" in agent_config.goal.lower()
    assert "researcher" in agent_config.backstory.lower()


async def test_execution_orchestrator_crew_multi_agent_routing():
    """Test ExecutionOrchestrator routing to CREW_MULTI_AGENT lane."""
    from domain.runtime.envelope import ClientContext

    orchestrator = ExecutionOrchestrator()

    envelope = ButlerRuntimeEnvelope(
        tenant_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        session_id="test-session",
        input=UserInput(type="text", content="Research the latest AI developments"),
        client_context=ClientContext(timezone="UTC"),
    )

    intent_result = MockIntentResult(
        execution_class=ExecutionClass.CREW_MULTI_AGENT,
        intent="research",
        metadata={
            "domain": "research",
            "complexity": "medium",
            "agent_roles": ["researcher", "analyst"],
        },
    )

    # This will fail if CrewAI is not installed, which is expected in test environment
    result = await orchestrator.execute(envelope, intent_result)

    # Should return an error about CrewAI not being installed
    assert result.execution_class == ExecutionClass.CREW_MULTI_AGENT
    # In test environment without CrewAI installed, this will return an error
    if "crewai_not_installed" in result.metadata.get("error", ""):
        assert "CrewAI not installed" in result.response


@pytest.mark.skipif(
    True,
    reason="Requires CrewAI installation and API keys",
)
def test_crewai_builder_build_crew():
    """Test building a CrewAI crew from domain requirements."""
    builder = CrewAIBuilder()

    domain_requirements = DomainRequirement(
        domain="research",
        complexity="medium",
        agent_roles=["researcher", "analyst"],
    )

    crew = builder.build_crew(
        domain_requirements=domain_requirements,
        user_message="Research the latest AI developments",
        context={"account_id": "test", "session_id": "test"},
    )

    assert crew is not None
    assert len(crew.agents) == 2
    assert len(crew.tasks) >= 1


@pytest.mark.skipif(
    True,
    reason="Requires CrewAI installation and API keys",
)
async def test_crewai_builder_execute_crew():
    """Test executing a CrewAI crew."""
    builder = CrewAIBuilder()

    domain_requirements = DomainRequirement(
        domain="research",
        complexity="medium",
        agent_roles=["researcher"],
    )

    crew = builder.build_crew(
        domain_requirements=domain_requirements,
        user_message="What is 2 + 2?",
        context={"account_id": "test", "session_id": "test"},
    )

    inputs = {
        "user_message": "What is 2 + 2?",
        "account_id": "test",
        "session_id": "test",
    }

    result = await builder.execute_crew(crew, inputs)

    assert "response" in result
    assert "metadata" in result
    assert result["metadata"].get("crew_execution") is True


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        # Run basic tests without CrewAI installation
        test_crewai_config()
        test_crew_agent_config()
        test_domain_requirement()
        test_crewai_builder_initialization()
        test_crewai_builder_get_default_roles()
        test_crewai_builder_get_agent_config()
        await test_execution_orchestrator_crew_multi_agent_routing()

        print("All basic tests passed!")

    asyncio.run(run_tests())
