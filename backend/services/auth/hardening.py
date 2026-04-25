"""Auth + Identity Hardening.

Phase G: Auth-profile rotation, secret-file pattern, persistent bindings.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuthProfile:
    """An authentication profile with rotation metadata."""

    profile_id: str
    user_id: str
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rotated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    rotation_interval_hours: int = 720  # 30 days default
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def should_rotate(self) -> bool:
        """Check if profile should be rotated."""
        age_hours = (datetime.now(UTC) - self.rotated_at).total_seconds() / 3600
        return age_hours >= self.rotation_interval_hours

    def is_expired(self) -> bool:
        """Check if profile is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


@dataclass
class SecretFile:
    """A secret file entry following the secret-file pattern."""

    secret_id: str
    name: str
    encrypted_value: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rotated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    rotation_interval_hours: int = 168  # 7 days default
    metadata: dict[str, Any] = field(default_factory=dict)

    def should_rotate(self) -> bool:
        """Check if secret should be rotated."""
        age_hours = (datetime.now(UTC) - self.rotated_at).total_seconds() / 3600
        return age_hours >= self.rotation_interval_hours

    def is_expired(self) -> bool:
        """Check if secret is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


@dataclass
class PersistentBinding:
    """A persistent binding for auth/identity (ACP pattern)."""

    binding_id: str
    user_id: str
    tenant_id: str
    service: str
    resource_id: str
    binding_type: str = "oauth"  # oauth, api_key, token
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if binding is valid."""
        if not self.is_active:
            return False
        if self.expires_at is None:
            return True
        return datetime.now(UTC) < self.expires_at


class AuthHardeningService:
    """Service for auth and identity hardening.

    This service:
    - Manages auth profile rotation
    - Implements secret-file pattern
    - Manages persistent bindings
    - Provides audit trail
    """

    def __init__(self):
        """Initialize the auth hardening service."""
        self._profiles: dict[str, AuthProfile] = {}
        self._secrets: dict[str, SecretFile] = {}
        self._bindings: dict[str, PersistentBinding] = {}

    def create_profile(
        self,
        user_id: str,
        tenant_id: str,
        rotation_interval_hours: int = 720,
    ) -> AuthProfile:
        """Create an auth profile.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            rotation_interval_hours: Rotation interval in hours

        Returns:
            Created profile
        """
        import uuid

        profile_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=rotation_interval_hours * 2)

        profile = AuthProfile(
            profile_id=profile_id,
            user_id=user_id,
            tenant_id=tenant_id,
            expires_at=expires_at,
            rotation_interval_hours=rotation_interval_hours,
        )

        self._profiles[profile_id] = profile
        logger.info("auth_profile_created", profile_id=profile_id)
        return profile

    def rotate_profile(self, profile_id: str) -> AuthProfile:
        """Rotate an auth profile.

        Args:
            profile_id: Profile identifier

        Returns:
            Rotated profile
        """
        profile = self._profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        profile.rotated_at = datetime.now(UTC)
        profile.expires_at = datetime.now(UTC) + timedelta(hours=profile.rotation_interval_hours * 2)

        logger.info("auth_profile_rotated", profile_id=profile_id)
        return profile

    def get_profile(self, profile_id: str) -> AuthProfile | None:
        """Get an auth profile.

        Args:
            profile_id: Profile identifier

        Returns:
            Profile or None
        """
        return self._profiles.get(profile_id)

    def create_secret(
        self,
        name: str,
        encrypted_value: str,
        rotation_interval_hours: int = 168,
    ) -> SecretFile:
        """Create a secret file entry.

        Args:
            name: Secret name
            encrypted_value: Encrypted secret value
            rotation_interval_hours: Rotation interval in hours

        Returns:
            Created secret
        """
        import uuid

        secret_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=rotation_interval_hours * 2)

        secret = SecretFile(
            secret_id=secret_id,
            name=name,
            encrypted_value=encrypted_value,
            expires_at=expires_at,
            rotation_interval_hours=rotation_interval_hours,
        )

        self._secrets[secret_id] = secret
        logger.info("secret_created", secret_id=secret_id, name=name)
        return secret

    def rotate_secret(self, secret_id: str, new_encrypted_value: str) -> SecretFile:
        """Rotate a secret.

        Args:
            secret_id: Secret identifier
            new_encrypted_value: New encrypted value

        Returns:
            Rotated secret
        """
        secret = self._secrets.get(secret_id)
        if not secret:
            raise ValueError(f"Secret not found: {secret_id}")

        secret.encrypted_value = new_encrypted_value
        secret.rotated_at = datetime.now(UTC)
        secret.expires_at = datetime.now(UTC) + timedelta(hours=secret.rotation_interval_hours * 2)

        logger.info("secret_rotated", secret_id=secret_id)
        return secret

    def get_secret(self, secret_id: str) -> SecretFile | None:
        """Get a secret.

        Args:
            secret_id: Secret identifier

        Returns:
            Secret or None
        """
        return self._secrets.get(secret_id)

    def create_binding(
        self,
        user_id: str,
        tenant_id: str,
        service: str,
        resource_id: str,
        binding_type: str = "oauth",
        expires_in_hours: int | None = None,
    ) -> PersistentBinding:
        """Create a persistent binding.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            service: Service name
            resource_id: Resource identifier
            binding_type: Type of binding
            expires_in_hours: Optional expiration in hours

        Returns:
            Created binding
        """
        import uuid

        binding_id = str(uuid.uuid4())
        expires_at = (
            datetime.now(UTC) + timedelta(hours=expires_in_hours)
            if expires_in_hours
            else None
        )

        binding = PersistentBinding(
            binding_id=binding_id,
            user_id=user_id,
            tenant_id=tenant_id,
            service=service,
            resource_id=resource_id,
            binding_type=binding_type,
            expires_at=expires_at,
        )

        self._bindings[binding_id] = binding
        logger.info("persistent_binding_created", binding_id=binding_id)
        return binding

    def get_binding(self, binding_id: str) -> PersistentBinding | None:
        """Get a persistent binding.

        Args:
            binding_id: Binding identifier

        Returns:
            Binding or None
        """
        return self._bindings.get(binding_id)

    def get_user_bindings(self, user_id: str) -> list[PersistentBinding]:
        """Get all bindings for a user.

        Args:
            user_id: User identifier

        Returns:
            List of bindings
        """
        return [b for b in self._bindings.values() if b.user_id == user_id]

    async def rotate_expired_profiles(self) -> int:
        """Rotate all expired profiles.

        Returns:
            Number of profiles rotated
        """
        rotated = 0
        for profile_id, profile in self._profiles.items():
            if profile.should_rotate():
                self.rotate_profile(profile_id)
                rotated += 1

        logger.info("expired_profiles_rotated", count=rotated)
        return rotated

    async def rotate_expired_secrets(self) -> int:
        """Rotate all expired secrets.

        Returns:
            Number of secrets rotated
        """
        # In production, generate new encrypted values
        rotated = 0
        for secret_id, secret in self._secrets.items():
            if secret.should_rotate():
                # Placeholder: would generate new encrypted value
                self.rotate_secret(secret_id, secret.encrypted_value)
                rotated += 1

        logger.info("expired_secrets_rotated", count=rotated)
        return rotated

    def invalidate_expired_bindings(self) -> int:
        """Invalidate all expired bindings.

        Returns:
            Number of bindings invalidated
        """
        invalidated = 0
        for binding in self._bindings.values():
            if not binding.is_valid():
                binding.is_active = False
                invalidated += 1

        logger.info("expired_bindings_invalidated", count=invalidated)
        return invalidated
