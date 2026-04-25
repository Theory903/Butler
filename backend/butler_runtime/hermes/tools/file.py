"""Butler-Hermes file tools.

File operations from Hermes that have been assimilated into Butler with
Butler workspace policy and governance.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ButlerHermesFileTools:
    """Butler-native file tools from Hermes.

    File operations with Butler workspace policy:
    - read_file: Read file contents
    - write_file: Write file contents
    - list_files: List directory contents
    - search_files: Search for files by pattern
    """

    def __init__(self, workspace_root: Path | None = None) -> None:
        """Initialize Butler file tools.

        Args:
            workspace_root: Root directory for file operations (for security)
        """
        self._workspace_root = workspace_root or Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to workspace root.

        Args:
            path: Path to resolve

        Returns:
            Resolved absolute path
        """
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self._workspace_root / resolved

        # Ensure path is within workspace root
        try:
            resolved.resolve().relative_to(self._workspace_root.resolve())
        except ValueError:
            raise ValueError(f"Path {path} is outside workspace root")

        return resolved

    async def read_file(self, path: str, max_bytes: int = 200_000) -> dict[str, Any]:
        """Read file contents.

        Args:
            path: File path
            max_bytes: Maximum bytes to read

        Returns:
            Dictionary with file contents or error
        """
        try:
            resolved_path = self._resolve_path(path)

            if not resolved_path.exists():
                return {
                    "path": str(resolved_path),
                    "content": None,
                    "error": f"File not found: {path}",
                }

            if not resolved_path.is_file():
                return {
                    "path": str(resolved_path),
                    "content": None,
                    "error": f"Not a file: {path}",
                }

            content = resolved_path.read_text(errors="replace")
            if len(content) > max_bytes:
                content = content[:max_bytes] + "\n\n[...content truncated...]"

            return {
                "path": str(resolved_path),
                "content": content,
                "size_bytes": len(content),
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Failed to read file {path}: {e}")
            return {
                "path": path,
                "content": None,
                "error": str(e),
            }

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write content to a file.

        Args:
            path: File path
            content: Content to write

        Returns:
            Dictionary with success status or error
        """
        try:
            resolved_path = self._resolve_path(path)

            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            resolved_path.write_text(content)

            return {
                "path": str(resolved_path),
                "bytes_written": len(content),
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Failed to write file {path}: {e}")
            return {
                "path": path,
                "bytes_written": 0,
                "error": str(e),
            }

    async def list_files(self, path: str = ".", recursive: bool = False) -> dict[str, Any]:
        """List directory contents.

        Args:
            path: Directory path
            recursive: Whether to list recursively

        Returns:
            Dictionary with file list or error
        """
        try:
            resolved_path = self._resolve_path(path)

            if not resolved_path.exists():
                return {
                    "path": str(resolved_path),
                    "files": [],
                    "error": f"Directory not found: {path}",
                }

            if not resolved_path.is_dir():
                return {
                    "path": str(resolved_path),
                    "files": [],
                    "error": f"Not a directory: {path}",
                }

            if recursive:
                files = [
                    str(p.relative_to(resolved_path))
                    for p in resolved_path.rglob("*")
                    if p.is_file()
                ]
            else:
                files = [str(p.relative_to(resolved_path)) for p in resolved_path.iterdir()]

            return {
                "path": str(resolved_path),
                "files": sorted(files),
                "count": len(files),
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Failed to list files in {path}: {e}")
            return {
                "path": path,
                "files": [],
                "error": str(e),
            }

    async def search_files(
        self, pattern: str, path: str = ".", case_sensitive: bool = False
    ) -> dict[str, Any]:
        """Search for files by pattern.

        Args:
            pattern: Search pattern (glob style)
            path: Directory to search
            case_sensitive: Whether search is case-sensitive

        Returns:
            Dictionary with matching files or error
        """
        try:
            resolved_path = self._resolve_path(path)

            if not resolved_path.exists():
                return {
                    "path": str(resolved_path),
                    "matches": [],
                    "error": f"Directory not found: {path}",
                }

            if not resolved_path.is_dir():
                return {
                    "path": str(resolved_path),
                    "matches": [],
                    "error": f"Not a directory: {path}",
                }

            # Use glob pattern matching
            import fnmatch

            matches = []
            for p in resolved_path.rglob("*"):
                if p.is_file():
                    rel_path = str(p.relative_to(resolved_path))
                    if case_sensitive:
                        if fnmatch.fnmatch(rel_path, pattern):
                            matches.append(rel_path)
                    else:
                        if fnmatch.fnmatch(rel_path.lower(), pattern.lower()):
                            matches.append(rel_path)

            return {
                "path": str(resolved_path),
                "pattern": pattern,
                "matches": sorted(matches),
                "count": len(matches),
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Failed to search files in {path}: {e}")
            return {
                "path": path,
                "pattern": pattern,
                "matches": [],
                "error": str(e),
            }
