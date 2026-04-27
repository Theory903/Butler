"""Credential pool system with load balancing and rotation."""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import random


class CredentialHealth(str, Enum):
    """Health status of a credential."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class Credential:
    """Represents a single API credential."""
    id: str
    provider: str
    key: str
    metadata: dict[str, Any] = field(default_factory=dict)
    health: CredentialHealth = CredentialHealth.HEALTHY
    last_used: float = field(default_factory=time.time)
    last_success: float = 0.0
    last_failure: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    rate_limit_until: float = 0.0
    
    def is_rate_limited(self) -> bool:
        """Check if credential is currently rate limited."""
        return time.time() < self.rate_limit_until
    
    def is_available(self) -> bool:
        """Check if credential is available for use."""
        return (
            self.health != CredentialHealth.UNHEALTHY
            and not self.is_rate_limited()
        )
    
    def record_success(self) -> None:
        """Record a successful usage."""
        self.last_success = time.time()
        self.last_used = time.time()
        self.success_count += 1
        self.failure_count = 0
        if self.health == CredentialHealth.DEGRADED:
            self.health = CredentialHealth.HEALTHY
    
    def record_failure(self, is_rate_limit: bool = False) -> None:
        """Record a failed usage."""
        self.last_failure = time.time()
        self.last_used = time.time()
        self.failure_count += 1
        
        if is_rate_limit:
            # Rate limit for 1 minute
            self.rate_limit_until = time.time() + 60.0
        
        # Update health based on failure pattern
        if self.failure_count >= 5:
            self.health = CredentialHealth.UNHEALTHY
        elif self.failure_count >= 2:
            self.health = CredentialHealth.DEGRADED


@dataclass
class PoolStats:
    """Statistics for a credential pool."""
    total_credentials: int = 0
    healthy_credentials: int = 0
    degraded_credentials: int = 0
    unhealthy_credentials: int = 0
    rate_limited_credentials: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0


@dataclass
class CredentialPool:
    """Pool of credentials with load balancing."""
    _credentials: dict[str, Credential] = field(default_factory=dict)
    _provider_creds: dict[str, list[str]] = field(default_factory=dict)
    _lru_queue: deque[str] = field(default_factory=deque)
    _strategy: str = "round_robin"  # round_robin, lru, health_based
    
    def add_credential(self, credential: Credential) -> None:
        """Add a credential to the pool."""
        self._credentials[credential.id] = credential
        
        if credential.provider not in self._provider_creds:
            self._provider_creds[credential.provider] = []
        self._provider_creds[credential.provider].append(credential.id)
    
    def get_next_credential(self, provider: str) -> Credential | None:
        """Get the next available credential for a provider using the configured strategy."""
        if provider not in self._provider_creds:
            return None
        
        credential_ids = self._provider_creds[provider]
        available_creds = [
            self._credentials[cid]
            for cid in credential_ids
            if self._credentials[cid].is_available()
        ]
        
        if not available_creds:
            return None
        
        if self._strategy == "round_robin":
            return self._select_round_robin(available_creds)
        elif self._strategy == "lru":
            return self._select_lru(available_creds)
        elif self._strategy == "health_based":
            return self._select_health_based(available_creds)
        else:
            return random.choice(available_creds)
    
    def _select_round_robin(self, credentials: list[Credential]) -> Credential:
        """Select credential using round-robin strategy."""
        # Simple round-robin: rotate through available credentials
        if not hasattr(self, '_round_robin_index'):
            self._round_robin_index = {}
        
        provider = credentials[0].provider
        if provider not in self._round_robin_index:
            self._round_robin_index[provider] = 0
        
        index = self._round_robin_index[provider] % len(credentials)
        self._round_robin_index[provider] += 1
        return credentials[index]
    
    def _select_lru(self, credentials: list[Credential]) -> Credential:
        """Select credential using least-recently-used strategy."""
        return min(credentials, key=lambda c: c.last_used)
    
    def _select_health_based(self, credentials: list[Credential]) -> Credential:
        """Select credential based on health status."""
        # Prefer healthy credentials, then degraded
        healthy = [c for c in credentials if c.health == CredentialHealth.HEALTHY]
        if healthy:
            return random.choice(healthy)
        
        degraded = [c for c in credentials if c.health == CredentialHealth.DEGRADED]
        if degraded:
            return random.choice(degraded)
        
        return random.choice(credentials)
    
    def mark_credential_success(self, credential_id: str) -> None:
        """Mark a credential as successfully used."""
        if credential_id in self._credentials:
            self._credentials[credential_id].record_success()
    
    def mark_credential_failed(self, credential_id: str, is_rate_limit: bool = False) -> None:
        """Mark a credential as failed."""
        if credential_id in self._credentials:
            self._credentials[credential_id].record_failure(is_rate_limit)
    
    def rotate_credential(self, provider: str) -> Credential | None:
        """Force rotation to a different credential for a provider."""
        if provider not in self._provider_creds:
            return None
        
        credential_ids = self._provider_creds[provider]
        available_creds = [
            self._credentials[cid]
            for cid in credential_ids
            if self._credentials[cid].is_available()
        ]
        
        if len(available_creds) <= 1:
            return None
        
        # Select a different credential than the last used
        last_used = self.get_next_credential(provider)
        if last_used:
            available_creds = [c for c in available_creds if c.id != last_used.id]
        
        if available_creds:
            return random.choice(available_creds)
        
        return None
    
    def get_pool_stats(self, provider: str) -> PoolStats:
        """Get statistics for a provider's credential pool."""
        if provider not in self._provider_creds:
            return PoolStats()
        
        credential_ids = self._provider_creds[provider]
        credentials = [self._credentials[cid] for cid in credential_ids]
        
        stats = PoolStats(
            total_credentials=len(credentials),
            healthy_credentials=sum(1 for c in credentials if c.health == CredentialHealth.HEALTHY),
            degraded_credentials=sum(1 for c in credentials if c.health == CredentialHealth.DEGRADED),
            unhealthy_credentials=sum(1 for c in credentials if c.health == CredentialHealth.UNHEALTHY),
            rate_limited_credentials=sum(1 for c in credentials if c.is_rate_limited()),
            total_requests=sum(c.success_count + c.failure_count for c in credentials),
            successful_requests=sum(c.success_count for c in credentials),
            failed_requests=sum(c.failure_count for c in credentials),
        )
        
        return stats
    
    def recover_unhealthy_credentials(self, provider: str, recovery_threshold: int = 300) -> int:
        """Attempt to recover unhealthy credentials that haven't failed recently."""
        if provider not in self._provider_creds:
            return 0
        
        now = time.time()
        recovered = 0
        
        for credential_id in self._provider_creds[provider]:
            cred = self._credentials[credential_id]
            if cred.health == CredentialHealth.UNHEALTHY:
                # Recover if no failures in the last recovery_threshold seconds
                if now - cred.last_failure > recovery_threshold:
                    cred.health = CredentialHealth.HEALTHY
                    cred.failure_count = 0
                    recovered += 1
        
        return recovered
    
    def set_strategy(self, strategy: str) -> None:
        """Set the load balancing strategy."""
        valid_strategies = {"round_robin", "lru", "health_based"}
        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy: {strategy}. Must be one of {valid_strategies}")
        self._strategy = strategy


def create_credential(
    provider: str,
    key: str,
    metadata: dict[str, Any] | None = None,
) -> Credential:
    """Create a new credential instance."""
    return Credential(
        id=str(uuid.uuid4()),
        provider=provider,
        key=key,
        metadata=metadata or {},
    )
