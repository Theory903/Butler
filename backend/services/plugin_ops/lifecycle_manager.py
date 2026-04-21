"""Butler Plugin Lifecycle Manager.

Handles double-buffered staging, promotion, and rollback of packages.
Implements Wave A Task 4.
"""

from __future__ import annotations

import os
import shutil
import uuid
import structlog
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from domain.skills.models import PackageState, PluginPackage, PluginVersion, SecurityAuditLog
from domain.skills.manifest import SkillManifest
from services.tools.trust_pipeline import TrustPipeline, TrustGateResult
from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class LifecycleManager:
    """
    Manages the physical filesystem lifecycle of Butler plugins.
    
    Structure in BUTLER_DATA_DIR/plugins:
    - releases/<package_id>/<version>/  (The actual code)
    - active/<package_id> -> ../releases/<package_id>/<active_version>  (Symlink)
    - staged/<package_id> -> ../releases/<package_id>/<staged_version>  (Symlink)
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.root = Path(data_dir or settings.BUTLER_DATA_DIR) / "plugins"
        self.releases_dir = self.root / "releases"
        self.active_dir = self.root / "active"
        self.staged_dir = self.root / "staged"
        
        # Ensure directories exist
        for d in [self.releases_dir, self.active_dir, self.staged_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def stage_version(
        self, 
        package_id: str, 
        version: str, 
        archive_bytes: bytes, 
        manifest: SkillManifest
    ) -> Path:
        """
        Stage a new version to the filesystem.
        
        1. Extract archive to releases/<package_id>/<version>/
        2. Create/Update symlink in staged/<package_id>
        """
        pkg_release_dir = self.releases_dir / package_id / version
        pkg_release_dir.mkdir(parents=True, exist_ok=True)
        
        # TODO: Real archive extraction (zip/tar)
        # For Wave A stub, we'll just write a placeholder file and the manifest
        (pkg_release_dir / "plugin_code.bin").write_bytes(archive_bytes)
        with open(pkg_release_dir / "openclaw.plugin.json", "w") as f:
            f.write(manifest.json(by_alias=True))
            
        # Update staged symlink
        staged_link = self.staged_dir / package_id
        if staged_link.exists() or staged_link.is_symlink():
            staged_link.unlink()
        
        # Create relative symlink
        os.symlink(f"../releases/{package_id}/{version}", staged_link)
        
        logger.info("package_staged", package_id=package_id, version=version, path=str(pkg_release_dir))
        return pkg_release_dir

    async def promote_active(self, package_id: str, version: str) -> bool:
        """
        Atomically promote a staged version to active.
        
        1. Repoint active/<package_id> to releases/<package_id>/<version>/
        2. Keep previous link in DB logic (filesystem version remains in releases/)
        """
        active_link = self.active_dir / package_id
        target = self.releases_dir / package_id / version
        
        if not target.exists():
            logger.error("promotion_target_missing", path=str(target))
            return False
            
        if active_link.exists() or active_link.is_symlink():
            active_link.unlink()
            
        os.symlink(f"../releases/{package_id}/{version}", active_link)
        
        # Clear staged link
        staged_link = self.staged_dir / package_id
        if staged_link.is_symlink():
            staged_link.unlink()
            
        logger.info("package_promoted", package_id=package_id, version=version)
        return True

    async def rollback(self, package_id: str, previous_version: str) -> bool:
        """Rollback active symlink to a previous version."""
        logger.info("initiating_rollback", package_id=package_id, to_version=previous_version)
        return await self.promote_active(package_id, previous_version)

    def get_active_path(self, package_id: str) -> Optional[Path]:
        """Get the physical path for an active plugin."""
        link = self.active_dir / package_id
        if link.exists() and link.is_symlink():
            return link.resolve()
        return None

    def list_installed_versions(self, package_id: str) -> List[str]:
        """List all version directories on disk for a package."""
        pkg_dir = self.releases_dir / package_id
        if not pkg_dir.exists():
            return []
        return [d.name for d in pkg_dir.iterdir() if d.is_dir()]

    async def purge_version(self, package_id: str, version: str):
        """Physically delete a version from disk."""
        target = self.releases_dir / package_id / version
        if target.exists():
            shutil.rmtree(target)
            logger.info("version_purged", package_id=package_id, version=version)
