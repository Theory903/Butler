"""Rate limiter with token bucket algorithm and burst allowance."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .config import RateLimitConfig


@dataclass
class RateLimiter:
    """Rate limiter using token bucket algorithm."""
    config: RateLimitConfig
    _tokens: float = field(init=False)
    _last_update: float = field(default_factory=time.time)
    _request_history: deque[float] = field(default_factory=deque)
    
    def __post_init__(self) -> None:
        """Initialize token bucket."""
        self._tokens = float(self.config.requests_per_minute)
    
    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        
        if elapsed > 0:
            # Refill rate: requests per minute / 60 seconds
            refill_rate = self.config.requests_per_minute / 60.0
            new_tokens = refill_rate * elapsed
            self._tokens = min(
                self._tokens + new_tokens,
                float(self.config.requests_per_minute)
            )
            self._last_update = now
    
    def can_request(self, burst: bool = False) -> bool:
        """Check if a request can be made."""
        self._refill_tokens()
        
        if burst:
            # Allow burst up to burst_allowance
            return self._tokens >= 0
        else:
            # Require at least 1 token
            return self._tokens >= 1.0
    
    def record_request(self) -> None:
        """Record a request and consume a token."""
        self._refill_tokens()
        
        if self._tokens >= 1.0:
            self._tokens -= 1.0
        
        # Track request timestamp for sliding window
        now = time.time()
        self._request_history.append(now)
        
        # Clean up old requests (older than 1 hour)
        cutoff = now - 3600.0
        while self._request_history and self._request_history[0] < cutoff:
            self._request_history.popleft()
    
    def get_wait_time(self) -> float:
        """Get the time to wait before the next request can be made."""
        self._refill_tokens()
        
        if self._tokens >= 1.0:
            return 0.0
        
        # Calculate time to refill 1 token
        refill_rate = self.config.requests_per_minute / 60.0
        needed = 1.0 - self._tokens
        wait_time = needed / refill_rate
        
        return max(0.0, wait_time)
    
    def get_request_count_minute(self) -> int:
        """Get number of requests in the last minute."""
        now = time.time()
        cutoff = now - 60.0
        
        count = sum(1 for ts in self._request_history if ts > cutoff)
        return count
    
    def get_request_count_hour(self) -> int:
        """Get number of requests in the last hour."""
        return len(self._request_history)
    
    def reset(self) -> None:
        """Reset the rate limiter."""
        self._tokens = float(self.config.requests_per_minute)
        self._last_update = time.time()
        self._request_history.clear()


@dataclass
class MultiProviderRateLimiter:
    """Rate limiter for multiple providers."""
    limiters: dict[str, RateLimiter] = field(default_factory=dict)
    default_config: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    def get_limiter(self, provider: str, config: RateLimitConfig | None = None) -> RateLimiter:
        """Get or create a rate limiter for a provider."""
        if provider not in self.limiters:
            limiter_config = config or self.default_config
            self.limiters[provider] = RateLimiter(config=limiter_config)
        return self.limiters[provider]
    
    def can_request(self, provider: str, burst: bool = False) -> bool:
        """Check if a request can be made for a provider."""
        limiter = self.get_limiter(provider)
        return limiter.can_request(burst=burst)
    
    def record_request(self, provider: str) -> None:
        """Record a request for a provider."""
        limiter = self.get_limiter(provider)
        limiter.record_request()
    
    def get_wait_time(self, provider: str) -> float:
        """Get the time to wait before the next request for a provider."""
        limiter = self.get_limiter(provider)
        return limiter.get_wait_time()
    
    def get_stats(self, provider: str) -> dict[str, int]:
        """Get rate limiting stats for a provider."""
        limiter = self.get_limiter(provider)
        return {
            "requests_last_minute": limiter.get_request_count_minute(),
            "requests_last_hour": limiter.get_request_count_hour(),
            "available_tokens": int(limiter._tokens),
        }
