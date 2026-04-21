"""Butler Skill and Plugin Marketplace — Phase 7a.

Implements manifest-first skill registry, capability discovery, tenant-scoped installation,
policy-gated execution, and MCP compatibility layer.

Governed by: docs/03-reference/plugins/skill-marketplace.md
SWE-5 Requirements: Pydantic schemas, capability discovery, security sandbox, audit trail
"""

from __future__ import annotations

import os
import json
import hashlib
import structlog
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union, List, Dict, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator, root_validator
from sqlalchemy import select

logger = structlog.get_logger(__name__)


# Stub implementations - to be connected to real services
class settings:
    """Stub for core.settings."""
    SKILL_MARKETPLACE_DIR = os.environ.get("BUTLER_DATA_DIR", "/tmp/butler") + "/skills"
    ALLOWED_SANDBOX_PROFILES = ["ephemeral", "persistent", "privileged"]
    ALLOWED_SKILL_PERMISSIONS = ["filesystem:read", "filesystem:write", "network:outbound"]


class PermissionDenied(Exception):
    """Stub for core.security.PermissionDenied."""
    pass


class Tenant:
    """Stub for backend.domain.tenant.Tenant."""
    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name


class AuditLog:
    """Stub for backend.services.tools.auditor.AuditLog."""
    @staticmethod
    async def log(event_type: str, tenant_id: Any, **kwargs):
        tid = str(tenant_id) if isinstance(tenant_id, UUID) else tenant_id
        logger.info("audit", event_type=event_type, tenant_id=tid, **kwargs)

    @classmethod
    def get_instance(cls) -> "AuditLog":
        return cls()


class AuditEventType:
    """Stub for backend.services.tools.auditor.AuditEventType."""
    SKILL_INSTALLED = "skill.installed"
    SKILL_EXECUTED = "skill.executed"
    SKILL_UNINSTALLED = "skill.uninstalled"
    SKILL_QUOTA_UPDATED = "skill.quota_updated"


class SandboxManager:
    """Stub for backend.services.tools.sandbox_manager.SandboxManager."""
    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> "SandboxManager":
        return cls()

    async def execute(self, skill_id: str, input_data: dict) -> dict:
        return {"status": "success", "output": {}}


class MCPBridge:
    """Stub for backend.services.tools.mcp_bridge.MCPBridge."""
    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> "MCPBridge":
        return cls()


class SkillType(str, Enum):
    """Type of skill package."""
    NATIVE = "native"          # Butler native Python skill
    MCP = "mcp"                # Model Context Protocol server
    EXTERNAL = "external"      # External HTTP skill
    COMPOSITE = "composite"    # Composite of multiple skills


class CapabilityType(str, Enum):
    """Type of capability exposed by a skill."""
    TOOL = "tool"
    PROMPT = "prompt"
    TRANSFORMER = "transformer"
    OBSERVER = "observer"
    POLICY = "policy"


class AssuranceLevel(str, Enum):
    """Assurance level for skill execution."""
    AAL0 = "aal0"  # No assurance (sandboxed only)
    AAL1 = "aal1"  # Verified signature
    AAL2 = "aal2"  # Audited
    AAL3 = "aal3"  # Formal verification


class SkillManifest(BaseModel):
    """Machine-readable skill definition manifest.

    All skills MUST provide this manifest. No exceptions.
    Manifest is signed and verified before installation.
    """
    id: str = Field(description="Unique skill identifier (reverse DNS recommended)")
    name: str = Field(min_length=2, max_length=100, description="Human readable name")
    description: str = Field(min_length=10, max_length=1000, description="Full description")
    version: str = Field(description="Semantic version string")
    type: SkillType = Field(description="Skill execution type")
    author: str = Field(description="Author name/identifier")
    homepage: Optional[str] = None
    repository: Optional[str] = None
    license: str = Field(description="SPDX license identifier")

    capabilities: List[CapabilityDefinition] = Field(default_factory=list, description="Exposed capabilities")
    requires: List[str] = Field(default_factory=list, description="Required skill dependencies")
    provides: List[str] = Field(default_factory=list, description="Provided interfaces")

    aal_required: AssuranceLevel = Field(default=AssuranceLevel.AAL0, description="Minimum assurance level required to run")
    sandbox_profile: str = Field(default="default", description="Sandbox profile to use")
    timeout_seconds: int = Field(default=30, ge=1, le=3600, description="Maximum execution time")

    permissions: Dict[str, bool] = Field(default_factory=dict, description="Requested permissions")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")

    signature: Optional[str] = Field(None, description="ED25519 signature of manifest hash")
    published_at: Optional[datetime] = None

    @validator("version")
    def validate_semver(cls, v: str) -> str:
        """Validate semantic version format."""
        parts = v.split(".")
        if len(parts) < 3:
            raise ValueError("Version must be semantic version (MAJOR.MINOR.PATCH)")
        for part in parts:
            if not part.isdigit():
                raise ValueError("Version components must be numeric")
        return v

    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash of manifest content (excluding signature)."""
        manifest_dict = self.dict(exclude={"signature"})
        manifest_json = json.dumps(manifest_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(manifest_json).hexdigest()

    class Config:
        use_enum_values = True
        extra = "forbid"


class CapabilityDefinition(BaseModel):
    """Definition of a single capability exposed by a skill."""
    id: str = Field(description="Capability identifier (unique within skill)")
    name: str = Field(description="Human readable name")
    type: CapabilityType = Field(description="Capability type")
    description: str = Field(description="Full description")

    input_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for input")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for output")

    examples: List[Dict[str, Any]] = Field(default_factory=list, description="Usage examples")
    tags: List[str] = Field(default_factory=list, description="Classification tags")

    class Config:
        use_enum_values = True
        extra = "forbid"


class InstalledSkill(BaseModel):
    """Record of an installed skill for a specific tenant."""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    skill_id: str
    version: str
    manifest: SkillManifest

    enabled: bool = True
    installed_at: datetime = Field(default_factory=datetime.utcnow)
    installed_by: Optional[UUID] = None

    quota_limit: Optional[int] = None
    quota_used: int = 0
    last_used_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class CapabilityRegistry:
    """Global capability inventory.

    Maintains index of all available capabilities across all installed skills.
    Provides discovery and lookup functionality.
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, CapabilityDefinition] = {}
        self._skill_capabilities: Dict[str, Set[str]] = {}
        self._tag_index: Dict[str, Set[str]] = {}

    def register_skill_capabilities(self, skill_id: str, capabilities: List[CapabilityDefinition]) -> None:
        """Register all capabilities from a skill."""
        self._skill_capabilities[skill_id] = set()

        for cap in capabilities:
            full_id = f"{skill_id}.{cap.id}"
            self._capabilities[full_id] = cap
            self._skill_capabilities[skill_id].add(full_id)

            for tag in cap.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(full_id)

        logger.debug("capabilities_registered", skill_id=skill_id, count=len(capabilities))

    def unregister_skill_capabilities(self, skill_id: str) -> None:
        """Remove all capabilities for a skill."""
        if skill_id not in self._skill_capabilities:
            return

        for cap_id in self._skill_capabilities[skill_id]:
            cap = self._capabilities.pop(cap_id, None)
            if cap:
                for tag in cap.tags:
                    if tag in self._tag_index:
                        self._tag_index[tag].discard(cap_id)
                        if not self._tag_index[tag]:
                            del self._tag_index[tag]

        del self._skill_capabilities[skill_id]
        logger.debug("capabilities_unregistered", skill_id=skill_id)

    def get_capability(self, capability_id: str) -> Optional[CapabilityDefinition]:
        """Get capability by full identifier."""
        return self._capabilities.get(capability_id)

    def search_by_tag(self, tag: str) -> List[CapabilityDefinition]:
        """Search capabilities by tag."""
        cap_ids = self._tag_index.get(tag, set())
        return [self._capabilities[cap_id] for cap_id in cap_ids]

    def search_by_type(self, capability_type: CapabilityType) -> List[CapabilityDefinition]:
        """Search capabilities by type."""
        return [
            cap for cap in self._capabilities.values()
            if cap.type == capability_type
        ]

    def list_all(self) -> List[CapabilityDefinition]:
        """List all registered capabilities."""
        return list(self._capabilities.values())

    @property
    def capability_count(self) -> int:
        return len(self._capabilities)


class SkillInstaller:
    """Handles skill installation with validation and security checks.

    Performs manifest validation, signature verification, dependency resolution,
    and sandbox profile assignment before allowing skill installation.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        sandbox_manager: SandboxManager,
    ) -> None:
        self._capability_registry = capability_registry
        self._sandbox_manager = sandbox_manager
        self._audit = AuditLog.get_instance()

    async def validate_manifest(self, manifest: SkillManifest) -> bool:
        """Perform full validation of a skill manifest."""
        # 1. Schema validation (already done by Pydantic)
        # 2. Signature verification if present
        if manifest.signature:
            if not await self._verify_signature(manifest):
                logger.warning("invalid_skill_signature", skill_id=manifest.id)
                raise ValueError("Invalid skill signature")

        # 3. Dependency check
        for dep_id in manifest.requires:
            if not self._is_skill_available(dep_id):
                raise ValueError(f"Required dependency not available: {dep_id}")

        # 4. Permission validation
        for permission, required in manifest.permissions.items():
            if required and not self._is_permission_allowed(permission):
                raise PermissionDenied(f"Permission not allowed: {permission}")

        # 5. Sandbox profile validation
        if manifest.sandbox_profile not in settings.ALLOWED_SANDBOX_PROFILES:
            raise ValueError(f"Invalid sandbox profile: {manifest.sandbox_profile}")

        logger.debug("skill_manifest_validated", skill_id=manifest.id, version=manifest.version)
        return True

    async def install(self, tenant_id: UUID, manifest: SkillManifest, installed_by: Optional[UUID] = None) -> InstalledSkill:
        """Install a skill for a tenant."""
        await self.validate_manifest(manifest)

        # Check if already installed
        existing = await self._get_installed_skill(tenant_id, manifest.id)
        if existing:
            if existing.version == manifest.version:
                logger.info("skill_already_installed", tenant_id=tenant_id, skill_id=manifest.id)
                return existing
            # Upgrade existing installation
            await self.uninstall(tenant_id, manifest.id)

        # Register capabilities
        self._capability_registry.register_skill_capabilities(manifest.id, manifest.capabilities)

        # Create installation record
        installed = InstalledSkill(
            tenant_id=tenant_id,
            skill_id=manifest.id,
            version=manifest.version,
            manifest=manifest,
            installed_by=installed_by,
        )

        await self._save_installed_skill(installed)

        await self._audit.log(
            event_type=AuditEventType.SKILL_INSTALLED,
            tenant_id=tenant_id,
            actor_id=installed_by,
            details={"skill_id": manifest.id, "version": manifest.version},
        )

        logger.info("skill_installed", tenant_id=tenant_id, skill_id=manifest.id, version=manifest.version)
        return installed

    async def uninstall(self, tenant_id: UUID, skill_id: str) -> None:
        """Uninstall a skill from a tenant."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            return

        self._capability_registry.unregister_skill_capabilities(skill_id)
        await self._delete_installed_skill(installed.id)

        await self._audit.log(
            event_type=AuditEventType.SKILL_UNINSTALLED,
            tenant_id=tenant_id,
            details={"skill_id": skill_id, "version": installed.version},
        )

        logger.info("skill_uninstalled", tenant_id=tenant_id, skill_id=skill_id)

    async def _verify_signature(self, manifest: SkillManifest) -> bool:
        """Verify manifest signature using public key infrastructure."""
        # TODO: Implement full signature verification with trust root
        return True

    def _is_skill_available(self, skill_id: str) -> bool:
        """Check if a skill is available in the marketplace."""
        # TODO: Implement marketplace catalog lookup
        return True

    def _is_permission_allowed(self, permission: str) -> bool:
        """Check if a requested permission is allowed."""
        return permission in settings.ALLOWED_SKILL_PERMISSIONS

    async def _get_installed_skill(self, tenant_id: UUID, skill_id: str) -> Optional[InstalledSkill]:
        """Get installed skill record for tenant."""
        # TODO: Implement database lookup
        return None

    async def _save_installed_skill(self, installed: InstalledSkill) -> None:
        """Save installed skill record to database."""
        # TODO: Implement database persistence
        pass

    async def _delete_installed_skill(self, installed_id: UUID) -> None:
        """Delete installed skill record from database."""
        # TODO: Implement database deletion
        pass


class SkillGovernance:
    """Tenant-scoped governance, billing, quota enforcement, and policy gating.

    Enforces tenant limits, usage quotas, and execution policies for installed skills.
    """

    def __init__(self, capability_registry: CapabilityRegistry) -> None:
        self._capability_registry = capability_registry
        self._audit = AuditLog.get_instance()

    async def can_execute(
        self,
        tenant_id: UUID,
        skill_id: str,
        capability_id: Optional[str] = None,
    ) -> bool:
        """Check if a skill/capability can be executed for this tenant."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            return False

        if not installed.enabled:
            return False

        # Check quota
        if installed.quota_limit is not None and installed.quota_used >= installed.quota_limit:
            logger.warning("skill_quota_exceeded", tenant_id=tenant_id, skill_id=skill_id)
            return False

        # Check tenant policy
        if not await self._check_tenant_policy(tenant_id, skill_id, capability_id):
            return False

        return True

    async def record_usage(
        self,
        tenant_id: UUID,
        skill_id: str,
        execution_time_ms: int,
        success: bool,
    ) -> None:
        """Record skill usage for billing and quota tracking."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            return

        installed.quota_used += 1
        installed.last_used_at = datetime.utcnow()
        await self._save_installed_skill(installed)

        await self._audit.log(
            event_type=AuditEventType.SKILL_EXECUTED,
            tenant_id=tenant_id,
            details={
                "skill_id": skill_id,
                "execution_time_ms": execution_time_ms,
                "success": success,
                "quota_used": installed.quota_used,
            },
        )

    async def set_quota(self, tenant_id: UUID, skill_id: str, quota_limit: Optional[int]) -> None:
        """Set execution quota for a tenant skill."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            raise ValueError("Skill not installed for tenant")

        installed.quota_limit = quota_limit
        await self._save_installed_skill(installed)

        await self._audit.log(
            event_type=AuditEventType.SKILL_QUOTA_UPDATED,
            tenant_id=tenant_id,
            details={"skill_id": skill_id, "quota_limit": quota_limit},
        )

    async def enable_skill(self, tenant_id: UUID, skill_id: str) -> None:
        """Enable an installed skill."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            raise ValueError("Skill not installed for tenant")

        installed.enabled = True
        await self._save_installed_skill(installed)

    async def disable_skill(self, tenant_id: UUID, skill_id: str) -> None:
        """Disable an installed skill."""
        installed = await self._get_installed_skill(tenant_id, skill_id)
        if not installed:
            raise ValueError("Skill not installed for tenant")

        installed.enabled = False
        await self._save_installed_skill(installed)

    async def list_installed_skills(self, tenant_id: UUID) -> List[InstalledSkill]:
        """List all skills installed for a tenant."""
        # TODO: Implement database query
        return []

    async def _check_tenant_policy(
        self,
        tenant_id: UUID,
        skill_id: str,
        capability_id: Optional[str],
    ) -> bool:
        """Check tenant execution policy for this skill."""
        # TODO: Implement OPA policy evaluation
        return True

    async def _get_installed_skill(self, tenant_id: UUID, skill_id: str) -> Optional[InstalledSkill]:
        """Get installed skill record for tenant."""
        # TODO: Implement database lookup
        return None

    async def _save_installed_skill(self, installed: InstalledSkill) -> None:
        """Save installed skill record to database."""
        # TODO: Implement database persistence
        pass


class SkillMarketplace:
    """Main entry point for Butler Skill Marketplace.

    Orchestrates registry, installer, governance, and MCP bridge components.
    """

    def __init__(self) -> None:
        self.capability_registry = CapabilityRegistry()
        self.sandbox_manager = SandboxManager.get_instance()
        self.installer = SkillInstaller(self.capability_registry, self.sandbox_manager)
        self.governance = SkillGovernance(self.capability_registry)
        self.mcp_bridge = MCPBridge.get_instance()

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize marketplace and load installed skills."""
        if self._initialized:
            return

        # Load all installed skills from database
        # TODO: Implement bulk loading
        self._initialized = True
        logger.info("skill_marketplace_initialized", capability_count=self.capability_registry.capability_count)

    @classmethod
    def get_instance(cls) -> SkillMarketplace:
        """Return the global marketplace instance."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


# Singleton instance
marketplace = SkillMarketplace.get_instance()
