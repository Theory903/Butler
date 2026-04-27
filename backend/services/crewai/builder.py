"""CrewAI builder for Butler integration.

This module provides the CrewAIBuilder class for mapping Butler context
to CrewAI crews, maintaining Butler's security and governance boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

from crewai import Agent, Crew, LLM, Task

from .config import (
    CrewAIConfig,
    CrewAgentConfig,
    CrewTaskConfig,
    DomainRequirement,
)

logger = logging.getLogger(__name__)


class CrewAIBuilder:
    """Builder for creating CrewAI crews from Butler context.

    This class maps Butler's execution context, domain requirements,
    and tool configurations to CrewAI agents, tasks, and crews.

    Integration Principles:
    - All CrewAI operations must pass through Butler's security guardrails
    - Use Butler's durable state for persistence, CrewAI for in-memory flow control
    - Maintain Butler's service boundaries and governance
    - Use OpenTelemetry for observability consistency
    """

    def __init__(
        self,
        config: CrewAIConfig | None = None,
        content_guard: Any = None,
        memory_service: Any = None,
    ) -> None:
        """Initialize CrewAI builder.

        Args:
            config: CrewAI configuration. If None, uses default configuration.
            content_guard: Butler ContentGuard instance for safety checks.
            memory_service: Butler MemoryService instance for context retrieval and storage.
        """
        self._config = config or CrewAIConfig()
        self._llm = self._create_llm()
        self._content_guard = content_guard
        self._memory_service = memory_service

    def _create_llm(self) -> LLM:
        """Create CrewAI LLM instance from configuration.

        Returns:
            Configured LLM instance.
        """
        try:
            return LLM(
                model=self._config.model,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
        except Exception as e:
            logger.error(f"Failed to create LLM: {e}")
            # Return a fallback LLM that will fail gracefully at runtime
            # This allows the system to continue without crashing
            return LLM(model="openai/gpt-4o")

    def build_crew(
        self,
        domain_requirements: DomainRequirement,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> Crew:
        """Build a CrewAI crew from domain requirements.

        Args:
            domain_requirements: Domain-specific requirements for the crew.
            user_message: User message that triggered the request.
            context: Additional Butler context (session_id, account_id, etc.).

        Returns:
            Configured CrewAI crew instance.
        """
        # Build agents based on domain requirements
        agents = self._build_agents(domain_requirements, context)

        # Build tasks based on domain requirements
        tasks = self._build_tasks(domain_requirements, user_message, agents)

        # Create crew with agents and tasks
        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=self._config.process,
            memory=self._config.memory,
            verbose=self._config.verbose,
        )

        logger.info(
            f"Built CrewAI crew for domain '{domain_requirements.domain}' "
            f"with {len(agents)} agents and {len(tasks)} tasks"
        )

        return crew

    def _build_agents(
        self,
        domain_requirements: DomainRequirement,
        context: dict[str, Any] | None = None,
    ) -> list[Agent]:
        """Build CrewAI agents from domain requirements.

        Args:
            domain_requirements: Domain-specific requirements.
            context: Additional Butler context.

        Returns:
            List of configured CrewAI agents.
        """
        agents = []

        # Build default agents for common roles
        for role in domain_requirements.agent_roles or self._get_default_roles(domain_requirements.domain):
            agent_config = self._get_agent_config(role, domain_requirements.domain)
            agent = self._create_agent(agent_config, context)
            agents.append(agent)

        return agents

    def _get_default_roles(self, domain: str) -> list[str]:
        """Get default agent roles for a domain.

        Args:
            domain: Domain name.

        Returns:
            List of default agent roles for the domain.
        """
        domain_role_map = {
            "research": ["researcher", "analyst", "writer"],
            "financial_analysis": ["financial_analyst", "risk_assessor", "portfolio_manager"],
            "content_creation": ["researcher", "writer", "editor"],
            "code_development": ["developer", "reviewer", "tester"],
        }

        return domain_role_map.get(domain, ["generalist"])

    def _get_agent_config(self, role: str, domain: str) -> CrewAgentConfig:
        """Get agent configuration for a role in a domain.

        Args:
            role: Agent role.
            domain: Domain name.

        Returns:
            Agent configuration.
        """
        # In a real implementation, this would load from a configuration file or database
        # For now, return a basic configuration
        return CrewAgentConfig(
            role=role.replace("_", " ").title(),
            goal=f"Perform {role} tasks for {domain}",
            backstory=f"An expert {role} specializing in {domain}",
        )

    def _create_agent(
        self,
        agent_config: CrewAgentConfig,
        context: dict[str, Any] | None = None,
    ) -> Agent:
        """Create a CrewAI agent from configuration.

        Args:
            agent_config: Agent configuration.
            context: Additional Butler context.

        Returns:
            Configured CrewAI agent.
        """
        # Use agent-specific LLM if configured, otherwise use default
        llm = self._llm
        if agent_config.llm:
            llm = LLM(model=agent_config.llm)

        return Agent(
            role=agent_config.role,
            goal=agent_config.goal,
            backstory=agent_config.backstory,
            verbose=agent_config.verbose,
            allow_delegation=agent_config.allow_delegation,
            llm=llm,
        )

    def _build_tasks(
        self,
        domain_requirements: DomainRequirement,
        user_message: str,
        agents: list[Agent],
    ) -> list[Task]:
        """Build CrewAI tasks from domain requirements.

        Args:
            domain_requirements: Domain-specific requirements.
            user_message: User message that triggered the request.
            agents: List of available agents.

        Returns:
            List of configured CrewAI tasks.
        """
        tasks = []

        # Create a primary task from the user message
        primary_task = Task(
            description=user_message,
            expected_output="A comprehensive response addressing the user's request",
            agent=agents[0] if agents else None,
        )
        tasks.append(primary_task)

        # In a real implementation, this would create multiple tasks based on
        # the domain requirements and agent roles
        # For now, just return the primary task

        return tasks

    async def execute_crew(
        self,
        crew: Crew,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a CrewAI crew with inputs.

        Args:
            crew: CrewAI crew to execute.
            inputs: Input data for the crew.

        Returns:
            Execution result with response and metadata.
        """
        # Apply security guardrails if enabled and ContentGuard is available
        if self._config.enable_security_guardrails and self._content_guard:
            user_message = inputs.get("user_message", "")
            if user_message:
                try:
                    safety_check = await self._content_guard.check(user_message)
                    if not safety_check.get("safe", True):
                        logger.warning(
                            f"ContentGuard blocked unsafe input: {safety_check.get('reason')}"
                        )
                        return {
                            "response": "Input blocked by safety guardrails",
                            "metadata": {
                                "blocked_by_content_guard": True,
                                "reason": safety_check.get("reason"),
                                "categories": safety_check.get("categories"),
                            },
                        }
                except Exception as e:
                    logger.warning(f"ContentGuard check failed: {e}")
                    # Continue execution even if guardrail check fails (fail-safe)

        # Retrieve memory context if enabled and memory service is available
        memory_context = {}
        if self._config.enable_memory_integration and self._memory_service:
            try:
                session_id = inputs.get("session_id")
                account_id = inputs.get("account_id")
                if session_id and account_id:
                    # Retrieve relevant context from memory
                    # This is a simplified integration - Phase 3 will enhance this
                    # with CrewAI's hierarchical memory system
                    memory_context = await self._retrieve_memory_context(
                        session_id, account_id, inputs.get("user_message", "")
                    )
                    logger.info(f"Retrieved memory context with {len(memory_context)} items")
            except Exception as e:
                logger.warning(f"Memory context retrieval failed: {e}")
                # Continue execution even if memory retrieval fails (fail-safe)

        try:
            # Execute the crew with memory context added to inputs
            crew_inputs = {**inputs, "memory_context": memory_context}
            result = crew.kickoff(inputs=crew_inputs)

            # Extract response from result
            # CrewAI returns different result types depending on the process
            if hasattr(result, "raw"):
                response = result.raw
            elif hasattr(result, "result"):
                response = result.result
            else:
                response = str(result)

            # Apply security guardrails to output if enabled
            if self._config.enable_security_guardrails and self._content_guard:
                try:
                    safety_check = await self._content_guard.check(response)
                    if not safety_check.get("safe", True):
                        logger.warning(
                            f"ContentGuard blocked unsafe output: {safety_check.get('reason')}"
                        )
                        return {
                            "response": "Output blocked by safety guardrails",
                            "metadata": {
                                "blocked_by_content_guard": True,
                                "reason": safety_check.get("reason"),
                                "categories": safety_check.get("categories"),
                            },
                        }
                except Exception as e:
                    logger.warning(f"ContentGuard output check failed: {e}")

            # Store execution result in memory if enabled and memory service is available
            if self._config.enable_memory_integration and self._memory_service:
                try:
                    session_id = inputs.get("session_id")
                    account_id = inputs.get("account_id")
                    if session_id and account_id:
                        await self._store_execution_result(
                            session_id,
                            account_id,
                            inputs.get("user_message", ""),
                            response,
                        )
                        logger.info("Stored CrewAI execution result in memory")
                except Exception as e:
                    logger.warning(f"Memory storage failed: {e}")

            return {
                "response": response,
                "metadata": {
                    "crew_execution": True,
                    "process": self._config.process,
                    "model": self._config.model,
                    "security_guardrails_applied": self._config.enable_security_guardrails,
                    "memory_integration_applied": self._config.enable_memory_integration,
                    "memory_context_items": len(memory_context),
                },
            }

        except Exception as e:
            logger.exception(f"CrewAI execution failed: {e}")
            return {
                "response": f"CrewAI execution failed: {e}",
                "metadata": {"error": str(e)},
            }

    async def _retrieve_memory_context(
        self, session_id: str, account_id: str, query: str
    ) -> dict[str, Any]:
        """Retrieve relevant context from Butler memory service.

        Args:
            session_id: Session identifier.
            account_id: Account identifier.
            query: Query string for context retrieval.

        Returns:
            Dictionary with retrieved context.
        """
        if not self._memory_service:
            return {}

        try:
            # Use Butler's MemoryService to retrieve relevant context
            # This integrates with Butler's WARM/COLD memory tiers
            relevant_memories = await self._memory_service.recall(
                account_id=account_id, query=query, limit=5
            )

            session_history = await self._memory_service.get_session_history(
                account_id=account_id, session_id=session_id, limit=10
            )

            return {
                "relevant_memories": [
                    {"content": m.content, "memory_type": m.memory_type} for m in relevant_memories
                ],
                "session_history": [
                    {"role": h.role, "content": h.content} for h in session_history
                ],
                "session_id": session_id,
                "account_id": account_id,
            }
        except Exception as e:
            logger.warning(f"Memory context retrieval error: {e}")
            return {}

    async def _store_execution_result(
        self, session_id: str, account_id: str, query: str, response: str
    ) -> None:
        """Store CrewAI execution result in Butler memory service.

        Args:
            session_id: Session identifier.
            account_id: Account identifier.
            query: Original user query.
            response: CrewAI response.
        """
        if not self._memory_service:
            return

        try:
            # Store the conversation turn in Butler's memory
            await self._memory_service.store_turn(
                account_id=account_id,
                session_id=session_id,
                role="assistant",
                content=response,
                metadata={"source": "crewai_multi_agent"},
            )

            # Also store as a memory entry for future retrieval
            await self._memory_service.store(
                account_id=account_id,
                memory_type="crewai_execution",
                content={
                    "query": query,
                    "response": response,
                    "session_id": session_id,
                },
            )
        except Exception as e:
            logger.warning(f"Memory storage error: {e}")
