"""
Integration tests for Encryption Service.

Tests AES-256-GCM encryption with key rotation.
"""

import pytest

from services.crypto.encryption_service import EncryptionAlgorithm, EncryptionService


class TestEncryptionService:
    """Test suite for EncryptionService."""

    @pytest.fixture
    def encryption_service(self, mock_secret_manager):
        """Create encryption service instance."""
        return EncryptionService(secret_manager=mock_secret_manager)

    @pytest.mark.asyncio
    async def test_generate_key(self, encryption_service):
        """Test key generation."""
        key = await encryption_service.generate_key(tenant_id="tenant-123")

        assert key.tenant_id == "tenant-123"
        assert key.algorithm == EncryptionAlgorithm.AES256_GCM
        assert key.is_active is True

    @pytest.mark.asyncio
    async def test_encrypt_decrypt(self, encryption_service):
        """Test encryption and decryption."""
        plaintext = b"Hello, World!"
        tenant_id = "tenant-123"

        encrypted = await encryption_service.encrypt(plaintext, tenant_id)
        decrypted = await encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    @pytest.mark.asyncio
    async def test_encrypt_json(self, encryption_service):
        """Test JSON encryption and decryption."""
        data = {"message": "Hello", "count": 42}
        tenant_id = "tenant-123"

        encrypted_b64 = await encryption_service.encrypt_json(data, tenant_id)
        decrypted = await encryption_service.decrypt_json(encrypted_b64)

        assert decrypted == data

    @pytest.mark.asyncio
    async def test_key_rotation(self, encryption_service):
        """Test key rotation."""
        tenant_id = "tenant-123"

        old_key = await encryption_service.generate_key(tenant_id)
        new_key = await encryption_service.rotate_key(tenant_id)

        assert new_key.tenant_id == tenant_id
        assert new_key.key_id != old_key.key_id

    @pytest.mark.asyncio
    async def test_delete_key(self, encryption_service):
        """Test key deletion."""
        tenant_id = "tenant-123"

        key = await encryption_service.generate_key(tenant_id)
        await encryption_service.delete_key(tenant_id, key.key_id)

        # Verify key is deleted
        with pytest.raises(ValueError):
            await encryption_service._get_key_bytes(tenant_id, key.key_id)
