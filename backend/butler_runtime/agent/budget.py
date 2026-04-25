"""Execution budget for Butler Unified Agent Runtime.

Adapted from Hermes IterationBudget with Butler-specific extensions.
"""

import threading


class ExecutionBudget:
    """Thread-safe execution budget for Butler agent loops.

    Each agent (parent or subagent) gets its own ExecutionBudget.
    The parent's budget is capped at max_iterations (default 90).
    Each subagent gets an independent budget capped at delegation.max_iterations
    (default 50) — this means total iterations across parent + subagents can exceed
    the parent's cap.

    execute_code (programmatic tool calling) iterations are refunded via refund()
    so they don't eat into the budget.
    """

    def __init__(
        self,
        max_total: int = 90,
        max_tokens: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        """Initialize execution budget.

        Args:
            max_total: Maximum number of agent loop iterations
            max_tokens: Maximum input/output tokens (optional)
            max_cost_usd: Maximum estimated cost in USD (optional)
        """
        if max_total <= 0:
            raise ValueError("max_total must be greater than 0")

        self.max_total = max_total
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd

        self._used = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._estimated_cost_usd = 0.0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Try to consume one iteration. Returns True if allowed."""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Give back one iteration (e.g., for execute_code turns)."""
        with self._lock:
            if self._used > 0:
                self._used -= 1

    def consume_tokens(self, input_tokens: int, output_tokens: int) -> bool:
        """Consume tokens if within budget. Returns True if allowed."""
        if self.max_tokens is None:
            return True

        with self._lock:
            projected = self._input_tokens + input_tokens + self._output_tokens + output_tokens
            if projected > self.max_tokens:
                return False
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            return True

    def consume_cost(self, cost_usd: float) -> bool:
        """Consume estimated cost if within budget. Returns True if allowed."""
        if self.max_cost_usd is None:
            return True

        with self._lock:
            projected = self._estimated_cost_usd + cost_usd
            if projected > self.max_cost_usd:
                return False
            self._estimated_cost_usd = projected
            return True

    @property
    def used(self) -> int:
        """Number of iterations used."""
        return self._used

    @property
    def remaining(self) -> int:
        """Number of iterations remaining."""
        with self._lock:
            return max(0, self.max_total - self._used)

    @property
    def input_tokens(self) -> int:
        """Input tokens used."""
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        """Output tokens used."""
        return self._output_tokens

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self._input_tokens + self._output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """Estimated cost in USD."""
        return self._estimated_cost_usd

    @property
    def remaining_tokens(self) -> int | None:
        """Tokens remaining (or None if no token budget)."""
        if self.max_tokens is None:
            return None
        with self._lock:
            return max(0, self.max_tokens - self._input_tokens - self._output_tokens)

    @property
    def remaining_cost_usd(self) -> float | None:
        """Cost remaining in USD (or None if no cost budget)."""
        if self.max_cost_usd is None:
            return None
        with self._lock:
            return max(0.0, self.max_cost_usd - self._estimated_cost_usd)

    def can_continue(self) -> bool:
        """Check if agent can continue execution."""
        if self.remaining <= 0:
            return False
        if self.remaining_tokens is not None and self.remaining_tokens <= 0:
            return False
        return not (self.remaining_cost_usd is not None and self.remaining_cost_usd <= 0)

    def reset(self) -> None:
        """Reset budget to initial state."""
        with self._lock:
            self._used = 0
            self._input_tokens = 0
            self._output_tokens = 0
            self._estimated_cost_usd = 0.0

    def __repr__(self) -> str:
        return (
            f"ExecutionBudget(used={self.used}/{self.max_total}, "
            f"tokens={self.total_tokens}, cost=${self.estimated_cost_usd:.4f})"
        )
