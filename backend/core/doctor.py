from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class DoctorCheck(BaseModel):
    id: str
    name: str
    status: str  # PASS, FAIL, FIXED, SKIPPED
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DoctorReport(BaseModel):
    ok: bool
    checks: list[DoctorCheck]
    timestamp: str


class ButlerDoctor:
    """Butler's self-healing diagnostic service.
    
    Ported from OpenClaw v3.1 Oracle-Grade patterns:
    - Deep permission auditing (0o700/0o600).
    - Auto-repair for infrastructure drift.
    - Baseline consistency checks.
    """

    def __init__(self) -> None:
        self.data_dir = Path(settings.BUTLER_DATA_DIR)
        # Define sensitive paths and their required modes
        self.permission_targets = [
            (self.data_dir, 0o700, "dir"),
            (self.data_dir / "mcp", 0o700, "dir"),
            (self.data_dir / "cron", 0o700, "dir"),
            (self.data_dir / "hermes", 0o700, "dir"),
            (self.data_dir / "sessions", 0o700, "dir"),
            (self.data_dir / "keys", 0o700, "dir"),
            (self.data_dir / "mcp" / "manifest.json", 0o600, "file"),
        ]

    async def diagnose(self, fix: bool = False) -> DoctorReport:
        """Run all diagnostic checks. Optionally auto-repair found issues."""
        checks: list[DoctorCheck] = []
        is_windows = os.name == "nt"

        # 1. Directory Structure & Permissions
        for path, mode, kind in self.permission_targets:
            checks.append(await self._check_path_security(path, mode, kind, fix, is_windows))

        # 2. Tool Sandboxing (Phase 8d)
        checks.append(await self._check_docker_runtime())

        # 2. Dependency Readiness
        # (Future: add probes for Neo4j, Qdrant here)

        all_ok = not any(c.status == "FAIL" for c in checks)
        
        from datetime import UTC, datetime
        return DoctorReport(
            ok=all_ok,
            checks=checks,
            timestamp=datetime.now(UTC).isoformat()
        )

    async def _check_path_security(
        self, path: Path, required_mode: int, kind: str, fix: bool, is_windows: bool
    ) -> DoctorCheck:
        check_id = f"perm_{path.name or 'root'}"
        check_name = f"Security: {path.relative_to(self.data_dir.parent) if path.is_absolute() else path}"

        if not path.exists():
            if fix:
                try:
                    if kind == "dir":
                        path.mkdir(parents=True, exist_ok=True, mode=required_mode)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.touch(mode=required_mode)
                    return DoctorCheck(id=check_id, name=check_name, status="FIXED", message=f"Created missing {kind}")
                except Exception as e:
                    return DoctorCheck(id=check_id, name=check_name, status="FAIL", message=f"Failed to create: {e}")
            return DoctorCheck(id=check_id, name=check_name, status="FAIL", message=f"Missing {kind}")

        # Permission check (Skip deep ACLs on Windows for now, focus on Unix/Mac as per user env)
        if is_windows:
            return DoctorCheck(id=check_id, name=check_name, status="SKIPPED", message="Deep permission check skipped on Windows")

        try:
            current_mode = stat.S_IMODE(os.lstat(path).st_mode)
            if current_mode != required_mode:
                if fix:
                    os.chmod(path, required_mode)
                    return DoctorCheck(
                        id=check_id, 
                        name=check_name, 
                        status="FIXED", 
                        message=f"Fixed mode {oct(current_mode)} -> {oct(required_mode)}"
                    )
                return DoctorCheck(
                    id=check_id, 
                    name=check_name, 
                    status="FAIL", 
                    message=f"Insecure mode: {oct(current_mode)} (required {oct(required_mode)})"
                )
        except Exception as e:
            return DoctorCheck(id=check_id, name=check_name, status="FAIL", message=f"Permission check failed: {e}")

        return DoctorCheck(id=check_id, name=check_name, status="PASS", message="OK")

    async def _check_docker_runtime(self) -> DoctorCheck:
        """Verify Docker binary and daemon readiness."""
        check_id = "sandbox_docker"
        check_name = "Perimeter: Docker Sandbox"
        
        try:
            from integrations.hermes.tools.environments.docker import find_docker
            import subprocess
            
            docker_exe = find_docker()
            if not docker_exe:
                return DoctorCheck(
                    id=check_id, 
                    name=check_name, 
                    status="DEGRADED", 
                    message="Docker CLI or daemon not found. High-risk tool sandboxing is DEGRADED."
                )
            
            # Check daemon
            result = subprocess.run(
                [docker_exe, "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return DoctorCheck(
                    id=check_id, 
                    name=check_name, 
                    status="DEGRADED", 
                    message="Docker daemon is not running or accessible.",
                    details={"stderr": result.stderr.strip()}
                )
                
            return DoctorCheck(id=check_id, name=check_name, status="PASS", message="Docker daemon is healthy")
            
        except Exception as e:
            return DoctorCheck(
                id=check_id, 
                name=check_name, 
                status="DEGRADED", 
                message=f"Docker probe failed: {type(e).__name__}"
            )
