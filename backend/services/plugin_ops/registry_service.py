"""Butler Plugin Registry Service.

The orchestrator for plugin discovery, installation, and lifecycle.
Implements the Wave A ecosystem logic.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.skills.manifest import SkillManifest
from domain.skills.models import PackageState, PluginPackage, PluginVersion, SecurityAuditLog

from .clawhub_client import ClawHubClient
from .lifecycle_manager import LifecycleManager
from .trust_pipeline import TrustPipeline

logger = structlog.get_logger(__name__)


class PluginRegistryService:
    """
    High-level service for managing the Butler plugin ecosystem.

    Ties together the remote client, security gates, and filesystem lifecycle.
    """

    def __init__(
        self,
        db: AsyncSession,
        client: ClawHubClient,
        trust_pipeline: TrustPipeline,
        lifecycle: LifecycleManager,
    ):
        self.db = db
        self.client = client
        self.trust_pipeline = trust_pipeline
        self.lifecycle = lifecycle

    async def install_package(self, package_id: str, version: str, actor_id: uuid.UUID) -> bool:
        """
        Full 4-gate installation flow.

        1. Fetch manifest and signature from ClawHub.
        2. Download archive.
        3. Run Trust Pipeline (Gates A-D).
        4. Stage to filesystem.
        5. Record Audit Log.
        """
        logger.info("initiating_install", package_id=package_id, version=version)

        try:
            # 1. Fetch metadata
            manifest_data = await self.client.get_manifest(package_id, version)
            signature = await self.client.get_signature(package_id, version)
            archive_bytes = await self.client.download_package(package_id, version)

            # Temporary archive path for scanning
            # In real impl, we'd use a temp file
            temp_path = Path(f"/tmp/butler_{package_id}_{version}.zip")
            temp_path.write_bytes(archive_bytes)

            # 2. Trust Pipeline (Gates A-D)
            gate_results = await self.trust_pipeline.verify_all(manifest_data, temp_path, signature)
            all_passed = all(r.success for r in gate_results)

            # 3. Create Audit Record
            audit = SecurityAuditLog(
                actor_id=actor_id,
                action="install",
                status="success" if all_passed else "failed",
                gate_results={
                    r.gate: {"success": r.success, "details": r.details, "error": r.error}
                    for r in gate_results
                },
                details={"package_id": package_id, "version": version},
            )

            if not all_passed:
                failed_gates = [r.gate for r in gate_results if not r.success]
                audit.error_message = f"Failed gates: {', '.join(failed_gates)}"
                self.db.add(audit)
                await self.db.commit()
                logger.error(
                    "install_failed_security_gates", package_id=package_id, failed=failed_gates
                )
                return False

            # 4. Filesystem Staging
            manifest = SkillManifest(**manifest_data)
            await self.lifecycle.stage_version(package_id, version, archive_bytes, manifest)

            # 5. DB Record
            stmt = select(PluginPackage).where(PluginPackage.package_id == package_id)
            res = await self.db.execute(stmt)
            pkg = res.scalar_one_or_none()

            if not pkg:
                pkg = PluginPackage(
                    package_id=package_id,
                    name=manifest.name,
                    publisher=manifest.author or "Unknown",
                    state=PackageState.STAGED,
                    risk_tier=manifest.risk_class,
                )
                self.db.add(pkg)
                await self.db.flush()

            ver = PluginVersion(
                package_id=pkg.id,
                version=version,
                manifest=manifest_data,
                archive_hash="sha256:TODO",  # In real impl, hash the bytes
                min_gateway_version=manifest.min_gateway_version,
                plugin_api_version=manifest.plugin_api_version,
            )
            self.db.add(ver)
            audit.package_id = pkg.id

            await self.db.commit()
            logger.info("install_completed", package_id=package_id, version=version)
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error("install_exception", error=str(e), package_id=package_id)
            return False

    async def promote_package(self, package_id: str, version: str) -> bool:
        """Promote a staged version to active."""
        success = await self.lifecycle.promote_active(package_id, version)
        if success:
            stmt = select(PluginPackage).where(PluginPackage.package_id == package_id)
            res = await self.db.execute(stmt)
            pkg = res.scalar_one()
            pkg.current_version = version
            pkg.state = PackageState.ACTIVE
            await self.db.commit()
        return success

    async def list_packages(self) -> list[PluginPackage]:
        stmt = select(PluginPackage)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
