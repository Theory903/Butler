from __future__ import annotations

import asyncio
import os
import shutil
import stat
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class DoctorStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    FIXED = "FIXED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"


class DoctorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    status: DoctorStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "name", "message")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned


class DoctorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = 0
    passed: int = 0
    failed: int = 0
    fixed: int = 0
    skipped: int = 0
    degraded: int = 0


class DoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    checks: list[DoctorCheck]
    summary: DoctorSummary
    timestamp: str


class ButlerDoctor:
    """Butler's self-healing diagnostic service.

    Design goals:
    - safe by default for sensitive filesystem paths
    - explicit, machine-readable results
    - repair only when fix=True
    - avoid blocking the event loop on external probes
    - never silently ignore security drift
    """

    def __init__(self) -> None:
        self.data_dir = Path(settings.BUTLER_DATA_DIR).expanduser().resolve()

        # Sensitive paths and expected modes.
        self.permission_targets: list[tuple[Path, int, str]] = [
            (self.data_dir, 0o700, "dir"),
            (self.data_dir / "mcp", 0o700, "dir"),
            (self.data_dir / "cron", 0o700, "dir"),
            (self.data_dir / "hermes", 0o700, "dir"),
            (self.data_dir / "sessions", 0o700, "dir"),
            (self.data_dir / "keys", 0o700, "dir"),
            (self.data_dir / "mcp" / "manifest.json", 0o600, "file"),
        ]

    async def diagnose(self, fix: bool = False) -> DoctorReport:
        """Run all diagnostic checks and optionally repair drift."""
        checks: list[DoctorCheck] = []
        is_windows = os.name == "nt"

        for path, mode, kind in self.permission_targets:
            checks.append(
                await self._check_path_security(
                    path=path,
                    required_mode=mode,
                    kind=kind,
                    fix=fix,
                    is_windows=is_windows,
                )
            )

        checks.append(await self._check_docker_runtime())

        summary = self._build_summary(checks)
        ok = summary.failed == 0

        report = DoctorReport(
            ok=ok,
            checks=checks,
            summary=summary,
            timestamp=datetime.now(UTC).isoformat(),
        )

        logger.info(
            "butler_doctor_completed",
            ok=report.ok,
            total=summary.total,
            passed=summary.passed,
            failed=summary.failed,
            fixed=summary.fixed,
            skipped=summary.skipped,
            degraded=summary.degraded,
            fix=fix,
        )
        return report

    async def _check_path_security(
        self,
        *,
        path: Path,
        required_mode: int,
        kind: str,
        fix: bool,
        is_windows: bool,
    ) -> DoctorCheck:
        check_id = self._make_check_id(path)
        check_name = f"Security: {self._display_path(path)}"

        try:
            self._validate_target_kind(kind)
        except ValueError as exc:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message=str(exc),
                details={"path": str(path), "kind": kind},
            )

        # Refuse symlinks for sensitive targets.
        if path.exists() and path.is_symlink():
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message="Sensitive path must not be a symlink",
                details={"path": str(path)},
            )

        if not path.exists():
            if not fix:
                return DoctorCheck(
                    id=check_id,
                    name=check_name,
                    status=DoctorStatus.FAIL,
                    message=f"Missing {kind}",
                    details={"path": str(path), "required_mode": oct(required_mode)},
                )

            try:
                await self._create_target(path=path, kind=kind, required_mode=required_mode)

                if not is_windows:
                    self._chmod_exact(path, required_mode)

                return DoctorCheck(
                    id=check_id,
                    name=check_name,
                    status=DoctorStatus.FIXED,
                    message=f"Created missing {kind}",
                    details={"path": str(path), "required_mode": oct(required_mode)},
                )
            except Exception as exc:
                logger.exception(
                    "doctor_create_target_failed",
                    path=str(path),
                    kind=kind,
                )
                return DoctorCheck(
                    id=check_id,
                    name=check_name,
                    status=DoctorStatus.FAIL,
                    message=f"Failed to create missing {kind}",
                    details={
                        "path": str(path),
                        "kind": kind,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

        if kind == "dir" and not path.is_dir():
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message="Expected directory but found different file type",
                details={"path": str(path)},
            )

        if kind == "file" and not path.is_file():
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message="Expected file but found different file type",
                details={"path": str(path)},
            )

        if is_windows:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.SKIPPED,
                message="Deep POSIX permission check skipped on Windows",
                details={"path": str(path), "required_mode": oct(required_mode)},
            )

        try:
            current_mode = stat.S_IMODE(os.lstat(path).st_mode)
        except Exception as exc:
            logger.exception("doctor_permission_stat_failed", path=str(path))
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message="Permission check failed",
                details={"path": str(path), "error": f"{type(exc).__name__}: {exc}"},
            )

        if current_mode == required_mode:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.PASS,
                message="OK",
                details={
                    "path": str(path),
                    "mode": oct(current_mode),
                    "required_mode": oct(required_mode),
                },
            )

        if not fix:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message=f"Insecure mode: {oct(current_mode)}",
                details={
                    "path": str(path),
                    "mode": oct(current_mode),
                    "required_mode": oct(required_mode),
                },
            )

        try:
            self._chmod_exact(path, required_mode)
            repaired_mode = stat.S_IMODE(os.lstat(path).st_mode)

            if repaired_mode != required_mode:
                return DoctorCheck(
                    id=check_id,
                    name=check_name,
                    status=DoctorStatus.FAIL,
                    message="Tried to repair mode but verification failed",
                    details={
                        "path": str(path),
                        "before_mode": oct(current_mode),
                        "after_mode": oct(repaired_mode),
                        "required_mode": oct(required_mode),
                    },
                )

            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FIXED,
                message=f"Fixed mode {oct(current_mode)} -> {oct(repaired_mode)}",
                details={
                    "path": str(path),
                    "before_mode": oct(current_mode),
                    "after_mode": oct(repaired_mode),
                    "required_mode": oct(required_mode),
                },
            )
        except Exception as exc:
            logger.exception("doctor_permission_fix_failed", path=str(path))
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.FAIL,
                message="Failed to repair permissions",
                details={
                    "path": str(path),
                    "before_mode": oct(current_mode),
                    "required_mode": oct(required_mode),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    async def _check_docker_runtime(self) -> DoctorCheck:
        """Verify Docker binary and daemon readiness without blocking the event loop."""
        check_id = "sandbox_docker"
        check_name = "Perimeter: Docker Sandbox"

        docker_exe = shutil.which("docker")
        if not docker_exe:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.DEGRADED,
                message="Docker CLI not found. High-risk sandboxing is degraded.",
                details={},
            )

        try:
            process = await asyncio.create_subprocess_exec(
                docker_exe,
                "version",
                "--format",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except TimeoutError:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.DEGRADED,
                message="Docker daemon probe timed out",
                details={"docker_exe": docker_exe},
            )
        except Exception as exc:
            logger.exception("doctor_docker_probe_failed")
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.DEGRADED,
                message="Docker probe failed",
                details={
                    "docker_exe": docker_exe,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

        if process.returncode != 0:
            return DoctorCheck(
                id=check_id,
                name=check_name,
                status=DoctorStatus.DEGRADED,
                message="Docker daemon is not running or not accessible",
                details={
                    "docker_exe": docker_exe,
                    "returncode": process.returncode,
                    "stderr": stderr.decode("utf-8", errors="replace").strip()[:1000],
                },
            )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        details: dict[str, Any] = {"docker_exe": docker_exe}
        if stdout_text:
            try:
                details["version"] = json_safe_loads(stdout_text)
            except Exception:
                details["raw_version"] = stdout_text[:1000]

        return DoctorCheck(
            id=check_id,
            name=check_name,
            status=DoctorStatus.PASS,
            message="Docker daemon is healthy",
            details=details,
        )

    async def _create_target(self, *, path: Path, kind: str, required_mode: int) -> None:
        if kind == "dir":
            path.mkdir(parents=True, exist_ok=True)
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch(exist_ok=True)
        self._chmod_exact(path, required_mode)

    def _chmod_exact(self, path: Path, required_mode: int) -> None:
        os.chmod(path, required_mode)

    def _validate_target_kind(self, kind: str) -> None:
        if kind not in {"dir", "file"}:
            raise ValueError(f"Unsupported target kind: {kind}")

    def _make_check_id(self, path: Path) -> str:
        raw = str(path).replace(os.sep, "_").replace(".", "_").strip("_")
        return f"perm_{raw or 'root'}"

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.data_dir.parent))
        except Exception:
            return str(path)

    def _build_summary(self, checks: list[DoctorCheck]) -> DoctorSummary:
        summary = DoctorSummary(total=len(checks))
        for check in checks:
            if check.status == DoctorStatus.PASS:
                summary.passed += 1
            elif check.status == DoctorStatus.FAIL:
                summary.failed += 1
            elif check.status == DoctorStatus.FIXED:
                summary.fixed += 1
            elif check.status == DoctorStatus.SKIPPED:
                summary.skipped += 1
            elif check.status == DoctorStatus.DEGRADED:
                summary.degraded += 1
        return summary


def json_safe_loads(value: str) -> Any:
    import json

    return json.loads(value)
