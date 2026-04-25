"""Butler Prompt Engineering for LangChain Agents.

Provides prompt templates, optimization, and management.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """A prompt template definition."""

    template_id: str
    name: str
    template: str
    variables: list[str] = field(default_factory=list)
    description: str = ""
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, **kwargs: Any) -> str:
        """Render the template with variables.

        Args:
            **kwargs: Variable values

        Returns:
            Rendered prompt
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as exc:
            logger.warning("prompt_render_failed", missing_var=str(exc))
            return self.template


@dataclass
class PromptOptimization:
    """Prompt optimization result."""

    original_prompt: str
    optimized_prompt: str
    improvements: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


class ButlerPromptLibrary:
    """Library of prompt templates.

    This library:
    - Stores prompt templates
    - Provides template lookup
    - Supports template versioning
    - Enables template sharing
    """

    def __init__(self):
        """Initialize the prompt library."""
        self._templates: dict[str, PromptTemplate] = {}
        self._load_builtin_templates()

    def _load_builtin_templates(self) -> None:
        """Load built-in prompt templates."""
        # System prompts
        self._templates["default_system"] = PromptTemplate(
            template_id="default_system",
            name="Default System Prompt",
            template="You are Butler, a helpful AI assistant designed to help users accomplish tasks efficiently and safely.",
            description="Default system prompt for Butler agents",
        )

        self._templates["tool_use_system"] = PromptTemplate(
            template_id="tool_use_system",
            name="Tool Use System Prompt",
            template="You are Butler, an AI assistant with access to various tools. Use tools when appropriate to accomplish user requests. Always explain your reasoning before calling tools.",
            description="System prompt for tool-enabled agents",
        )

        # User interaction prompts
        self._templates["greeting"] = PromptTemplate(
            template_id="greeting",
            name="Greeting Template",
            template="Hello! I'm Butler, your AI assistant. How can I help you today, {user_name}?",
            variables=["user_name"],
            description="Greeting prompt with user name",
        )

        self._templates["task_acknowledgment"] = PromptTemplate(
            template_id="task_acknowledgment",
            name="Task Acknowledgment",
            template="I'll help you with: {task}. Let me work on this step by step.",
            variables=["task"],
            description="Acknowledgment when accepting a task",
        )

        # Tool-specific prompts
        self._templates["tool_call_explanation"] = PromptTemplate(
            template_id="tool_call_explanation",
            name="Tool Call Explanation",
            template="I need to use the {tool_name} tool to {purpose}. Here's why: {reasoning}",
            variables=["tool_name", "purpose", "reasoning"],
            description="Template for explaining tool calls",
        )

        # Memory prompts
        self._templates["context_injection"] = PromptTemplate(
            template_id="context_injection",
            name="Context Injection",
            template="Relevant context from your memory:\n{context}\n\nUse this information to provide better responses.",
            variables=["context"],
            description="Template for injecting memory context",
        )

        logger.info("builtin_prompt_templates_loaded", count=len(self._templates))

    def register_template(self, template: PromptTemplate) -> None:
        """Register a prompt template.

        Args:
            template: Prompt template
        """
        self._templates[template.template_id] = template
        logger.info("prompt_template_registered", template_id=template.template_id)

    def get_template(self, template_id: str) -> PromptTemplate | None:
        """Get a template by ID.

        Args:
            template_id: Template ID

        Returns:
            Prompt template or None
        """
        return self._templates.get(template_id)

    def render_template(self, template_id: str, **kwargs: Any) -> str:
        """Render a template.

        Args:
            template_id: Template ID
            **kwargs: Variable values

        Returns:
            Rendered prompt
        """
        template = self.get_template(template_id)
        if not template:
            return ""

        return template.render(**kwargs)

    def list_templates(self, category: str | None = None) -> list[PromptTemplate]:
        """List templates with optional category filter.

        Args:
            category: Optional category filter

        Returns:
            List of templates
        """
        templates = list(self._templates.values())

        if category:
            templates = [t for t in templates if category in t.template_id]

        return templates

    def delete_template(self, template_id: str) -> bool:
        """Delete a template.

        Args:
            template_id: Template ID

        Returns:
            True if deleted
        """
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info("prompt_template_deleted", template_id=template_id)
            return True

        return False


class ButlerPromptOptimizer:
    """Optimizer for prompt engineering.

    This optimizer:
    - Analyzes prompt quality
    - Suggests improvements
    - Optimizes for clarity
    - Provides metrics
    """

    def __init__(self):
        """Initialize the prompt optimizer."""
        self._optimization_rules = self._load_optimization_rules()

    def _load_optimization_rules(self) -> list[dict[str, Any]]:
        """Load optimization rules."""
        return [
            {
                "rule": "clarity",
                "description": "Ensure prompt is clear and unambiguous",
                "check": lambda p: len(p.split()) > 10 and "?" in p or "." in p,
            },
            {
                "rule": "specificity",
                "description": "Use specific language instead of vague terms",
                "check": lambda p: "thing" not in p.lower() and "stuff" not in p.lower(),
            },
            {
                "rule": "context",
                "description": "Provide sufficient context",
                "check": lambda p: len(p) > 50,
            },
            {
                "rule": "format",
                "description": "Use proper formatting and structure",
                "check": lambda p: "\n" in p or " " in p,
            },
        ]

    def optimize_prompt(self, prompt: str, context: dict[str, Any] | None = None) -> PromptOptimization:
        """Optimize a prompt.

        Args:
            prompt: Original prompt
            context: Optional context

        Returns:
            Optimization result
        """
        improvements = []
        optimized = prompt

        # Apply optimization rules
        for rule in self._optimization_rules:
            if not rule["check"](prompt):
                improvements.append(rule["description"])
                optimized = self._apply_rule(optimized, rule["rule"])

        optimization = PromptOptimization(
            original_prompt=prompt,
            optimized_prompt=optimized,
            improvements=improvements,
            metrics=self._compute_metrics(optimized),
        )

        logger.info("prompt_optimized", improvements=len(improvements))
        return optimization

    def _apply_rule(self, prompt: str, rule: str) -> str:
        """Apply an optimization rule.

        Args:
            prompt: Prompt to optimize
            rule: Rule name

        Returns:
            Optimized prompt
        """
        # Simple rule implementations
        if rule == "clarity":
            # Add clarification if needed
            if "?" not in prompt and "." not in prompt:
                prompt += ". Please be specific."
        elif rule == "specificity":
            # Replace vague terms
            prompt = prompt.replace("thing", "item").replace("stuff", "items")
        elif rule == "context":
            # Add context if too short
            if len(prompt) < 50:
                prompt = f"Given the following context: {prompt}"
        elif rule == "format":
            # Add structure if needed
            if "\n" not in prompt:
                prompt = f"{prompt}\n\nPlease respond in a clear, structured manner."

        return prompt

    def _compute_metrics(self, prompt: str) -> dict[str, float]:
        """Compute prompt metrics.

        Args:
            prompt: Prompt to analyze

        Returns:
            Metrics dictionary
        """
        return {
            "length": len(prompt),
            "word_count": len(prompt.split()),
            "sentence_count": prompt.count(".") + prompt.count("?") + prompt.count("!"),
            "avg_word_length": sum(len(w) for w in prompt.split()) / len(prompt.split()) if prompt.split() else 0,
        }

    def compare_prompts(self, prompt1: str, prompt2: str) -> dict[str, Any]:
        """Compare two prompts.

        Args:
            prompt1: First prompt
            prompt2: Second prompt

        Returns:
            Comparison result
        """
        metrics1 = self._compute_metrics(prompt1)
        metrics2 = self._compute_metrics(prompt2)

        return {
            "prompt1_metrics": metrics1,
            "prompt2_metrics": metrics2,
            "length_diff": metrics2["length"] - metrics1["length"],
            "word_count_diff": metrics2["word_count"] - metrics1["word_count"],
        }


class ButlerPromptEngine:
    """Combined prompt engineering system.

    This engine:
    - Combines library and optimizer
    - Provides unified interface
    - Supports prompt chaining
    - Manages prompt versions
    """

    def __init__(self):
        """Initialize the prompt engine."""
        self._library = ButlerPromptLibrary()
        self._optimizer = ButlerPromptOptimizer()
        self._prompt_versions: dict[str, list[str]] = {}

    @property
    def library(self) -> ButlerPromptLibrary:
        """Get the prompt library."""
        return self._library

    @property
    def optimizer(self) -> ButlerPromptOptimizer:
        """Get the prompt optimizer."""
        return self._optimizer

    def create_chain(self, template_ids: list[str]) -> str:
        """Create a prompt chain from templates.

        Args:
            template_ids: List of template IDs

        Returns:
            Combined prompt
        """
        prompts = []
        for tid in template_ids:
            template = self._library.get_template(tid)
            if template:
                prompts.append(template.template)

        return "\n\n".join(prompts)

    def optimize_and_render(
        self,
        template_id: str,
        optimize: bool = True,
        **kwargs: Any,
    ) -> str:
        """Optimize and render a template.

        Args:
            template_id: Template ID
            optimize: Whether to optimize
            **kwargs: Variable values

        Returns:
            Rendered and optionally optimized prompt
        """
        prompt = self._library.render_template(template_id, **kwargs)

        if optimize:
            optimization = self._optimizer.optimize_prompt(prompt)
            prompt = optimization.optimized_prompt

        return prompt

    def save_prompt_version(self, prompt_id: str, prompt: str) -> str:
        """Save a prompt version.

        Args:
            prompt_id: Prompt ID
            prompt: Prompt content

        Returns:
            Version ID
        """
        import uuid
        version_id = str(uuid.uuid4())

        if prompt_id not in self._prompt_versions:
            self._prompt_versions[prompt_id] = []

        self._prompt_versions[prompt_id].append(version_id)

        # Store version (in production, this would use persistent storage)
        logger.info("prompt_version_saved", prompt_id=prompt_id, version_id=version_id)
        return version_id

    def get_prompt_versions(self, prompt_id: str) -> list[str]:
        """Get versions for a prompt.

        Args:
            prompt_id: Prompt ID

        Returns:
            List of version IDs
        """
        return self._prompt_versions.get(prompt_id, []).copy()

    def get_engine_status(self) -> dict[str, Any]:
        """Get engine status.

        Returns:
            Engine status
        """
        return {
            "template_count": len(self._library._templates),
            "optimization_rules": len(self._optimizer._optimization_rules),
            "versioned_prompts": len(self._prompt_versions),
        }
