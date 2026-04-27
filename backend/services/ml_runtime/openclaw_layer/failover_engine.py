"""Failover engine with exponential backoff and circuit breaker."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

from .config import RetryConfig, CircuitBreakerConfig


T = TypeVar("T")


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class RetryPolicy:
    """Retry policy configuration."""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 30.0
    jitter: bool = True
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt with exponential backoff."""
        delay = self.initial_delay_seconds * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay_seconds)
        
        if self.jitter:
            # Add ±25% jitter to prevent thundering herd
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor
        
        return delay


@dataclass
class CircuitBreaker:
    """Circuit breaker for preventing cascading failures."""
    config: CircuitBreakerConfig
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_calls: int = 0
    
    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.config.half_open_max_calls:
                # Circuit has recovered
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failed in half-open, go back to open
            self.state = CircuitBreakerState.OPEN
            self.half_open_calls = 0
        elif self.failure_count >= self.config.failure_threshold:
            # Threshold reached, open circuit
            self.state = CircuitBreakerState.OPEN
    
    def can_attempt(self) -> bool:
        """Check if a call can be attempted."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if time.time() - self.last_failure_time > self.config.recovery_timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls
        
        return False
    
    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0


@dataclass
class FailoverEngine:
    """Failover engine with retry logic and circuit breaker."""
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    circuit_breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    
    def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a provider."""
        if provider not in self.circuit_breakers:
            self.circuit_breakers[provider] = CircuitBreaker(
                config=CircuitBreakerConfig()
            )
        return self.circuit_breakers[provider]
    
    async def execute_with_retry(
        self,
        func: Callable[[], T] | Callable[[], Any],
        provider: str = "default",
    ) -> Any:
        """Execute a function with retry logic and circuit breaker protection."""
        circuit_breaker = self.get_circuit_breaker(provider)
        
        if not circuit_breaker.can_attempt():
            raise RuntimeError(f"Circuit breaker is open for provider: {provider}")
        
        last_exception: Exception | None = None
        
        for attempt in range(1, self.retry_policy.max_retries + 1):
            try:
                # Check if function is async
                if asyncio.iscoroutinefunction(func):
                    result = await func()
                else:
                    result = func()
                circuit_breaker.record_success()
                return result
            except Exception as e:
                last_exception = e
                circuit_breaker.record_failure()
                
                # Don't retry on the last attempt
                if attempt == self.retry_policy.max_retries:
                    break
                
                # Calculate delay and wait
                delay = self.retry_policy.calculate_delay(attempt)
                await asyncio.sleep(delay)
        
        # All retries exhausted
        if last_exception:
            raise last_exception
        raise RuntimeError("All retry attempts exhausted without exception")
    
    def switch_provider(
        self,
        failed_provider: str,
        available_providers: list[str],
    ) -> str | None:
        """Select an alternative provider from available options."""
        if not available_providers:
            return None
        
        # Filter out the failed provider
        alternatives = [p for p in available_providers if p != failed_provider]
        
        if not alternatives:
            return None
        
        # Select provider with healthy circuit breaker
        healthy_providers = [
            p for p in alternatives
            if self.get_circuit_breaker(p).can_attempt()
        ]
        
        if healthy_providers:
            return random.choice(healthy_providers)
        
        # Fallback to any available provider
        return random.choice(alternatives)
    
    def health_check(self, provider: str, check_func: Callable[[], bool]) -> bool:
        """Perform a health check on a provider."""
        try:
            is_healthy = check_func()
            circuit_breaker = self.get_circuit_breaker(provider)
            
            if is_healthy:
                circuit_breaker.record_success()
            else:
                circuit_breaker.record_failure()
            
            return is_healthy
        except Exception:
            circuit_breaker = self.get_circuit_breaker(provider)
            circuit_breaker.record_failure()
            return False
    
    def get_provider_health(self, provider: str) -> dict[str, Any]:
        """Get health status for a provider."""
        circuit_breaker = self.get_circuit_breaker(provider)
        
        return {
            "provider": provider,
            "state": circuit_breaker.state.value,
            "failure_count": circuit_breaker.failure_count,
            "last_failure_time": circuit_breaker.last_failure_time,
            "can_attempt": circuit_breaker.can_attempt(),
        }
