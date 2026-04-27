"""Repository for tenant provider configuration and custom API keys."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.ml_providers import (
    ProviderType,
    TenantProviderPreference,
    TenantCustomApiKey,
    ProviderConfigRequest,
    CustomApiKeyRequest,
)
from infrastructure.ml.models import (
    TenantProviderPreference as DBTenantProviderPreference,
    TenantCustomApiKey as DBTenantCustomApiKey,
)


class ProviderConfigRepository:
    """Repository for managing tenant provider configuration."""
    
    def __init__(self, db_session: AsyncSession, encryption_key: str | None = None):
        self.db = db_session
        if encryption_key is None:
            raise ValueError(
                "PROVIDER_ENCRYPTION_KEY is required for provider configuration. "
                "Set it in your environment variables. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        self._fernet = Fernet(encryption_key.encode())
    
    def _encrypt_key(self, key: str) -> str:
        """Encrypt an API key."""
        return self._fernet.encrypt(key.encode()).decode()
    
    def _decrypt_key(self, encrypted_key: str) -> str:
        """Decrypt an API key."""
        return self._fernet.decrypt(encrypted_key.encode()).decode()
    
    async def get_tenant_preference(
        self,
        tenant_id: str,
    ) -> TenantProviderPreference | None:
        """Get tenant's provider preference."""
        result = await self.db.execute(
            select(DBTenantProviderPreference).where(
                DBTenantProviderPreference.tenant_id == tenant_id
            )
        )
        db_pref = result.scalar_one_or_none()
        
        if not db_pref:
            return None
        
        return TenantProviderPreference(
            tenant_id=db_pref.tenant_id,
            provider=ProviderType(db_pref.provider),
            model=db_pref.model,
            use_custom_key=db_pref.use_custom_key,
            custom_key_id=db_pref.custom_key_id,
            created_at=db_pref.created_at,
            updated_at=db_pref.updated_at,
            metadata=db_pref.extra_metadata or {},
        )
    
    async def set_tenant_preference(
        self,
        tenant_id: str,
        request: ProviderConfigRequest,
    ) -> TenantProviderPreference:
        """Set tenant's provider preference."""
        # Check if preference exists
        result = await self.db.execute(
            select(DBTenantProviderPreference).where(
                DBTenantProviderPreference.tenant_id == tenant_id
            )
        )
        existing = result.scalar_one_or_none()
        
        now = datetime.utcnow()
        
        if existing:
            # Update existing
            await self.db.execute(
                update(DBTenantProviderPreference)
                .where(DBTenantProviderPreference.tenant_id == tenant_id)
                .values(
                    provider=request.provider.value,
                    model=request.model,
                    use_custom_key=request.use_custom_key,
                    custom_key_id=request.custom_key_id,
                    updated_at=now,
                )
            )
        else:
            # Create new
            db_pref = DBTenantProviderPreference(
                tenant_id=tenant_id,
                provider=request.provider.value,
                model=request.model,
                use_custom_key=request.use_custom_key,
                custom_key_id=request.custom_key_id,
                created_at=now,
                updated_at=now,
                extra_metadata={},
            )
            self.db.add(db_pref)
        
        await self.db.commit()
        
        return TenantProviderPreference(
            tenant_id=tenant_id,
            provider=request.provider,
            model=request.model,
            use_custom_key=request.use_custom_key,
            custom_key_id=request.custom_key_id,
            created_at=now,
            updated_at=now,
            metadata={},
        )
    
    async def delete_tenant_preference(self, tenant_id: str) -> bool:
        """Delete tenant's provider preference."""
        result = await self.db.execute(
            delete(DBTenantProviderPreference).where(
                DBTenantProviderPreference.tenant_id == tenant_id
            )
        )
        await self.db.commit()
        return result.rowcount > 0
    
    async def get_custom_keys(
        self,
        tenant_id: str,
        provider: ProviderType | None = None,
    ) -> list[TenantCustomApiKey]:
        """Get custom API keys for a tenant."""
        query = select(DBTenantCustomApiKey).where(
            DBTenantCustomApiKey.tenant_id == tenant_id
        )
        
        if provider:
            query = query.where(DBTenantCustomApiKey.provider == provider.value)
        
        result = await self.db.execute(query)
        db_keys = result.scalars().all()
        
        return [
            TenantCustomApiKey(
                id=key.id,
                tenant_id=key.tenant_id,
                provider=ProviderType(key.provider),
                key_name=key.key_name,
                encrypted_key=key.encrypted_key,  # Keep encrypted
                created_at=key.created_at,
                last_used_at=key.last_used_at,
                is_active=key.is_active,
                metadata=key.extra_metadata or {},
            )
            for key in db_keys
        ]
    
    async def add_custom_key(
        self,
        tenant_id: str,
        request: CustomApiKeyRequest,
    ) -> TenantCustomApiKey:
        """Add a custom API key for a tenant."""
        key_id = f"{tenant_id}_{request.provider.value}_{request.key_name}"
        
        db_key = DBTenantCustomApiKey(
            id=key_id,
            tenant_id=tenant_id,
            provider=request.provider.value,
            key_name=request.key_name,
            encrypted_key=self._encrypt_key(request.api_key.get_secret_value()),
            created_at=datetime.utcnow(),
            last_used_at=None,
            is_active=True,
            extra_metadata=request.metadata,
        )
        
        self.db.add(db_key)
        await self.db.commit()
        
        return TenantCustomApiKey(
            id=key_id,
            tenant_id=tenant_id,
            provider=request.provider,
            key_name=request.key_name,
            encrypted_key=db_key.encrypted_key,  # Keep encrypted
            created_at=db_key.created_at,
            last_used_at=db_key.last_used_at,
            is_active=db_key.is_active,
            metadata=request.metadata,
        )
    
    async def get_custom_key(
        self,
        tenant_id: str,
        key_id: str,
    ) -> TenantCustomApiKey | None:
        """Get a specific custom API key (decrypted)."""
        result = await self.db.execute(
            select(DBTenantCustomApiKey).where(
                DBTenantCustomApiKey.id == key_id,
                DBTenantCustomApiKey.tenant_id == tenant_id,
            )
        )
        db_key = result.scalar_one_or_none()
        
        if not db_key:
            return None
        
        return TenantCustomApiKey(
            id=db_key.id,
            tenant_id=db_key.tenant_id,
            provider=ProviderType(db_key.provider),
            key_name=db_key.key_name,
            encrypted_key=db_key.encrypted_key,
            created_at=db_key.created_at,
            last_used_at=db_key.last_used_at,
            is_active=db_key.is_active,
            metadata=db_key.extra_metadata or {},
        )
    
    async def delete_custom_key(
        self,
        tenant_id: str,
        key_id: str,
    ) -> bool:
        """Delete a custom API key."""
        result = await self.db.execute(
            delete(DBTenantCustomApiKey).where(
                DBTenantCustomApiKey.id == key_id,
                DBTenantCustomApiKey.tenant_id == tenant_id,
            )
        )
        await self.db.commit()
        return result.rowcount > 0
    
    async def update_last_used(
        self,
        tenant_id: str,
        key_id: str,
    ) -> bool:
        """Update last used timestamp for a custom key."""
        result = await self.db.execute(
            update(DBTenantCustomApiKey)
            .where(
                DBTenantCustomApiKey.id == key_id,
                DBTenantCustomApiKey.tenant_id == tenant_id,
            )
            .values(last_used_at=datetime.utcnow())
        )
        await self.db.commit()
        return result.rowcount > 0
