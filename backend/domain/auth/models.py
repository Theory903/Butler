"""Auth domain models — SQLAlchemy ORM.

Implements the full identity schema from docs/02-services/data.md.
These models own the persistence for:
  - accounts
  - identities (password, passkey, OIDC providers)
  - passkey_credentials (WebAuthn)
  - sessions (device-bound, assurance-levelled)
  - refresh_token_families (rotation + reuse detection)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Principal(Base):
    """The root of the identity graph — represents the human/legal entity (sub)."""

    __tablename__ = "principals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="principal", cascade="all, delete-orphan"
    )
    identities: Mapped[list["Identity"]] = relationship(
        "Identity", back_populates="principal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Principal id={self.id} email={self.email!r}>"


class Account(Base):
    """Butler Account — representing a specific persona or context (aid)."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="Personal")
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    principal: Mapped["Principal"] = relationship("Principal", back_populates="accounts")
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r}>"


class Identity(Base):
    """Authentication identity — one principal can have many.

    identity_type: password | passkey | google | apple | github
    identifier:    email address, provider subject, etc.
    """

    __tablename__ = "identities"
    __table_args__ = (
        UniqueConstraint("identity_type", "identifier", name="uq_identities_type_identifier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier: Mapped[str] = mapped_column(String(512), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    principal: Mapped["Principal"] = relationship("Principal", back_populates="identities")

    def __repr__(self) -> str:
        return f"<Identity {self.identity_type}:{self.identifier!r}>"


class PasskeyCredential(Base):
    """WebAuthn passkey credential bound to a principal."""

    __tablename__ = "passkey_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    aaguid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    principal: Mapped["Principal"] = relationship("Principal")

class Session(Base):
    """Auth session — device-bound, assurance-levelled, expiry-tracked."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    active_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)
    assurance_level: Mapped[str] = mapped_column(String(8), nullable=False, default="aal1")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Timeouts
    idle_timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    principal: Mapped["Principal"] = relationship("Principal")
    account: Mapped["Account"] = relationship("Account", back_populates="sessions")
    token_families: Mapped[list["TokenFamily"]] = relationship(
        "TokenFamily", back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        if self.revoked_at or now > self.expires_at:
            return False
        
        # Idle timeout check
        if self.idle_timeout and (now - self.last_seen_at).total_seconds() > self.idle_timeout:
            return False
            
        return True


class TokenFamily(Base):
    """Refresh token family — tracks rotation and detects reuse."""

    __tablename__ = "refresh_token_families"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    
    # Lineage tracking
    parent_token_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lineage_root: Mapped[str | None] = mapped_column(String(128), nullable=True)
    revoked_branch_root: Mapped[str | None] = mapped_column(String(128), nullable=True)
    
    rotation_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    session: Mapped["Session"] = relationship("Session", back_populates="token_families")

    @property
    def is_valid(self) -> bool:
        return self.invalidated_at is None


class VoiceProfile(Base):
    """Voice fingerprint for speaker identification bound to a principal."""

    __tablename__ = "voice_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    embedding: Mapped[dict] = mapped_column(JSON, nullable=False)  # List[float] stored as JSON
    sample_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    principal: Mapped["Principal"] = relationship("Principal")


class OAuthClient(Base):
    """Registered OAuth applications authorized to use Butler as an IdP."""

    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    client_secret: Mapped[str | None] = mapped_column(String(120))
    client_name: Mapped[str] = mapped_column(String(120), nullable=False)
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)  # Space-separated
    grant_types: Mapped[str] = mapped_column(Text, nullable=False)   # Space-separated
    response_types: Mapped[str] = mapped_column(Text, nullable=False) # Space-separated
    scope: Mapped[str] = mapped_column(Text, nullable=False)          # Space-separated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<OAuthClient id={self.client_id!r}>"


class OAuthCode(Base):
    """Temporary authorization codes (grants) for OIDC flow."""

    __tablename__ = "oauth_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    redirect_uri: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    # PKCE
    code_challenge: Mapped[str | None] = mapped_column(String(128))
    code_challenge_method: Mapped[str | None] = mapped_column(String(48))
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<OAuthCode code={self.code!r}>"


class RecoveryCode(Base):
    """Argon2id-hashed backup recovery code bound to a principal.

    A principal has at most 10 active codes. Redeeming one invalidates all others.
    """

    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(256), nullable=False)  # Argon2id hash
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    principal: Mapped["Principal"] = relationship("Principal")

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.invalidated_at is None

    def __repr__(self) -> str:
        return f"<RecoveryCode principal={self.principal_id}>"


class PasswordResetToken(Base):
    """One-time password reset token — 15-minute TTL, revokes all sessions on use."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex digest
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    principal: Mapped["Principal"] = relationship("Principal")

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        return self.used_at is None and not self.is_expired()

    def __repr__(self) -> str:
        return f"<PasswordResetToken principal={self.principal_id} expires={self.expires_at}>"