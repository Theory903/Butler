"""
Encryption Service - Data-at-Rest Encryption with Key Rotation

Implements AES-256-GCM encryption for sensitive data.
Supports automatic key rotation and multi-tenant key isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from infrastructure.secret_manager import SecretManager

logger = structlog.get_logger(__name__)


class EncryptionAlgorithm(StrEnum):
    """Supported encryption algorithms."""

    AES256_GCM = "aes256_gcm"


@dataclass(frozen=True, slots=True)
class EncryptedData:
    """Encrypted data with metadata."""

    ciphertext: bytes
    nonce: bytes
    key_id: str
    algorithm: EncryptionAlgorithm
    tenant_id: str
    encrypted_at: datetime


@dataclass(frozen=True, slots=True)
class EncryptionKey:
    """Encryption key metadata."""

    key_id: str
    tenant_id: str
    algorithm: EncryptionAlgorithm
    created_at: datetime
    expires_at: datetime | None
    is_active: bool


class EncryptionService:
    """
    Encryption service for data-at-rest protection.

    Features:
    - AES-256-GCM encryption
    - Tenant-scoped keys
    - Automatic key rotation
    - Key versioning
    """

    def __init__(
        self,
        secret_manager: SecretManager,
        default_key_ttl_days: int = 90,
    ) -> None:
        """Initialize encryption service."""
        self._secret_manager = secret_manager
        self._default_key_ttl_days = default_key_ttl_days
        self._key_cache: dict[str, bytes] = {}  # key_id -> key bytes

    def _key_secret_name(self, tenant_id: str, key_id: str) -> str:
        """Generate secret name for encryption key."""
        return f"encryption/{tenant_id}/{key_id}"

    def _master_key_secret_name(self, tenant_id: str) -> str:
        """Generate secret name for master key."""
        return f"encryption/master/{tenant_id}"

    async def _get_master_key(self, tenant_id: str) -> bytes:
        """Get or create master key for tenant."""
        secret_name = self._master_key_secret_name(tenant_id)

        try:
            master_key = await self._secret_manager.get_secret(secret_name)
            if master_key:
                return master_key.encode()
        except Exception:
            pass

        # Generate new master key
        import os

        master_key = os.urandom(32)  # 256-bit master key

        await self._secret_manager.create_secret(
            name=secret_name,
            secret=master_key.hex(),
            description=f"Master encryption key for tenant {tenant_id}",
            tags=["encryption", "master", f"tenant:{tenant_id}"],
        )

        logger.info(
            "encryption_master_key_created",
            tenant_id=tenant_id,
        )

        return master_key

    async def _derive_key(
        self,
        master_key: bytes,
        key_id: str,
        context: str | None = None,
    ) -> bytes:
        """Derive encryption key from master key using HKDF."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=key_id.encode() if key_id else b"",
            info=context.encode() if context else b"encryption",
            backend=default_backend(),
        )
        return hkdf.derive(master_key)

    async def generate_key(
        self,
        tenant_id: str,
        ttl_days: int | None = None,
    ) -> EncryptionKey:
        """
        Generate a new encryption key for tenant.

        Args:
            tenant_id: Tenant UUID
            ttl_days: Key TTL in days (None for no expiry)

        Returns:
            Encryption key metadata
        """
        key_id = f"key_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{tenant_id[:8]}"

        master_key = await self._get_master_key(tenant_id)
        derived_key = await self._derive_key(master_key, key_id, context=tenant_id)

        # Store derived key in secret manager
        secret_name = self._key_secret_name(tenant_id, key_id)
        await self._secret_manager.create_secret(
            name=secret_name,
            secret=derived_key.hex(),
            description=f"Encryption key {key_id} for tenant {tenant_id}",
            tags=["encryption", "data_key", f"tenant:{tenant_id}", f"key_id:{key_id}"],
        )

        expires_at = datetime.now(UTC) + timedelta(days=ttl_days) if ttl_days else None

        key = EncryptionKey(
            key_id=key_id,
            tenant_id=tenant_id,
            algorithm=EncryptionAlgorithm.AES256_GCM,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            is_active=True,
        )

        # Cache the key
        self._key_cache[key_id] = derived_key

        logger.info(
            "encryption_key_generated",
            tenant_id=tenant_id,
            key_id=key_id,
            expires_at=expires_at.isoformat() if expires_at else None,
        )

        return key

    async def get_active_key(self, tenant_id: str) -> EncryptionKey | None:
        """
        Get active encryption key for tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Active encryption key or None
        """
        # For simplicity, return the most recent key
        # In production, this would query the database for active keys
        try:
            await self._get_master_key(tenant_id)
            key_id = f"key_{datetime.now(UTC).strftime('%Y%m%d')}_{tenant_id[:8]}"

            # Check if key exists in secret manager
            secret_name = self._key_secret_name(tenant_id, key_id)
            try:
                await self._secret_manager.get_secret(secret_name)
            except Exception:
                # Key doesn't exist, generate it
                return await self.generate_key(tenant_id)

            return EncryptionKey(
                key_id=key_id,
                tenant_id=tenant_id,
                algorithm=EncryptionAlgorithm.AES256_GCM,
                created_at=datetime.now(UTC),
                expires_at=None,
                is_active=True,
            )
        except Exception:
            return None

    async def _get_key_bytes(self, tenant_id: str, key_id: str) -> bytes:
        """Get key bytes from cache or secret manager."""
        if key_id in self._key_cache:
            return self._key_cache[key_id]

        secret_name = self._key_secret_name(tenant_id, key_id)
        secret = await self._secret_manager.get_secret(secret_name)

        if secret:
            key_bytes = bytes.fromhex(secret)
            self._key_cache[key_id] = key_bytes
            return key_bytes

        raise ValueError(f"Encryption key {key_id} not found for tenant {tenant_id}")

    async def encrypt(
        self,
        plaintext: bytes,
        tenant_id: str,
        key_id: str | None = None,
    ) -> EncryptedData:
        """
        Encrypt data for tenant.

        Args:
            plaintext: Data to encrypt
            tenant_id: Tenant UUID
            key_id: Specific key ID (None for active key)

        Returns:
            Encrypted data with metadata
        """
        if key_id is None:
            key = await self.get_active_key(tenant_id)
            if not key:
                key = await self.generate_key(tenant_id)
            key_id = key.key_id
        else:
            key = EncryptionKey(
                key_id=key_id,
                tenant_id=tenant_id,
                algorithm=EncryptionAlgorithm.AES256_GCM,
                created_at=datetime.now(UTC),
                expires_at=None,
                is_active=True,
            )

        key_bytes = await self._get_key_bytes(tenant_id, key_id)

        aesgcm = AESGCM(key_bytes)
        nonce = AESGCM.generate_nonce(96)  # 96-bit nonce
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        encrypted_data = EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=key_id,
            algorithm=key.algorithm,
            tenant_id=tenant_id,
            encrypted_at=datetime.now(UTC),
        )

        logger.debug(
            "data_encrypted",
            tenant_id=tenant_id,
            key_id=key_id,
            size_bytes=len(plaintext),
        )

        return encrypted_data

    async def decrypt(
        self,
        encrypted_data: EncryptedData,
    ) -> bytes:
        """
        Decrypt data.

        Args:
            encrypted_data: Encrypted data with metadata

        Returns:
            Decrypted plaintext
        """
        key_bytes = await self._get_key_bytes(encrypted_data.tenant_id, encrypted_data.key_id)

        aesgcm = AESGCM(key_bytes)

        try:
            plaintext = aesgcm.decrypt(
                encrypted_data.nonce,
                encrypted_data.ciphertext,
                None,
            )

            logger.debug(
                "data_decrypted",
                tenant_id=encrypted_data.tenant_id,
                key_id=encrypted_data.key_id,
                size_bytes=len(plaintext),
            )

            return plaintext
        except Exception as exc:
            logger.error(
                "decryption_failed",
                tenant_id=encrypted_data.tenant_id,
                key_id=encrypted_data.key_id,
                error=str(exc),
            )
            raise ValueError("Decryption failed") from exc

    async def rotate_key(
        self,
        tenant_id: str,
        reencrypt: bool = True,
    ) -> EncryptionKey:
        """
        Rotate encryption key for tenant.

        Args:
            tenant_id: Tenant UUID
            reencrypt: Whether to reencrypt all data with new key

        Returns:
            New encryption key
        """
        old_key = await self.get_active_key(tenant_id)
        if not old_key:
            return await self.generate_key(tenant_id)

        # Generate new key
        new_key = await self.generate_key(tenant_id)

        # Mark old key as inactive (in production, update database)
        logger.info(
            "encryption_key_rotated",
            tenant_id=tenant_id,
            old_key_id=old_key.key_id,
            new_key_id=new_key.key_id,
        )

        # In production, this would trigger reencryption of all data
        # with the new key if reencrypt=True

        return new_key

    async def encrypt_json(
        self,
        data: dict[str, Any],
        tenant_id: str,
        key_id: str | None = None,
    ) -> str:
        """
        Encrypt JSON data and return base64-encoded result.

        Args:
            data: JSON data to encrypt
            tenant_id: Tenant UUID
            key_id: Specific key ID

        Returns:
            Base64-encoded encrypted data with metadata
        """
        import base64

        plaintext = json.dumps(data).encode()
        encrypted = await self.encrypt(plaintext, tenant_id, key_id)

        # Encode as JSON for storage
        wrapper = {
            "ciphertext": base64.b64encode(encrypted.ciphertext).decode(),
            "nonce": base64.b64encode(encrypted.nonce).decode(),
            "key_id": encrypted.key_id,
            "algorithm": encrypted.algorithm,
            "tenant_id": encrypted.tenant_id,
            "encrypted_at": encrypted.encrypted_at.isoformat(),
        }

        return base64.b64encode(json.dumps(wrapper).encode()).decode()

    async def decrypt_json(
        self,
        encrypted_b64: str,
    ) -> dict[str, Any]:
        """
        Decrypt base64-encoded JSON data.

        Args:
            encrypted_b64: Base64-encoded encrypted data

        Returns:
            Decrypted JSON data
        """
        import base64

        wrapper_bytes = base64.b64decode(encrypted_b64)
        wrapper = json.loads(wrapper_bytes)

        encrypted_data = EncryptedData(
            ciphertext=base64.b64decode(wrapper["ciphertext"]),
            nonce=base64.b64decode(wrapper["nonce"]),
            key_id=wrapper["key_id"],
            algorithm=wrapper["algorithm"],
            tenant_id=wrapper["tenant_id"],
            encrypted_at=datetime.fromisoformat(wrapper["encrypted_at"]),
        )

        plaintext = await self.decrypt(encrypted_data)
        return json.loads(plaintext.decode())

    async def delete_key(self, tenant_id: str, key_id: str) -> None:
        """
        Delete encryption key.

        Args:
            tenant_id: Tenant UUID
            key_id: Key ID to delete
        """
        secret_name = self._key_secret_name(tenant_id, key_id)
        await self._secret_manager.delete_secret(secret_name)

        # Remove from cache
        if key_id in self._key_cache:
            del self._key_cache[key_id]

        logger.info(
            "encryption_key_deleted",
            tenant_id=tenant_id,
            key_id=key_id,
        )
