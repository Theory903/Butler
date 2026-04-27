"""
Butler-native file tools module.

Provides LLM agent file manipulation tools (read, write, list) using
Butler-native file operations instead of Hermes terminal backends.
This is a Butler-native implementation that replaces Hermes file_tools.py
to avoid deep Hermes dependencies.
"""

import errno
import logging
import os

from langchain.butler_file_operations import ButlerFileOperations

import structlog

logger = structlog.get_logger(__name__)


# Expected write errors for permission handling
_EXPECTED_WRITE_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}

# Read-size guard: cap the character count returned to the model
_DEFAULT_MAX_READ_CHARS = 100_000
_max_read_chars_cached: int | None = None


def _get_max_read_chars() -> int:
    """Return the configured max characters per file read."""
    global _max_read_chars_cached
    if _max_read_chars_cached is not None:
        return _max_read_chars_cached
    _max_read_chars_cached = _DEFAULT_MAX_READ_CHARS
    return _max_read_chars_cached


# Device path blocklist — reading these hangs the process
_BLOCKED_DEVICE_PATHS = frozenset(
    {
        "/dev/zero",
        "/dev/random",
        "/dev/urandom",
        "/dev/full",
        "/dev/stdin",
        "/dev/tty",
        "/dev/console",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/fd/0",
        "/dev/fd/1",
        "/dev/fd/2",
    }
)


def _is_blocked_device_path(path: str) -> bool:
    """Check if path is a blocked device path."""
    return path in _BLOCKED_DEVICE_PATHS


# Global file operations instance (can be replaced with Butler sandbox manager later)
_file_ops_instance: ButlerFileOperations | None = None


def _get_file_ops() -> ButlerFileOperations:
    """Get or create the file operations instance."""
    global _file_ops_instance
    if _file_ops_instance is None:
        _file_ops_instance = ButlerFileOperations()
    return _file_ops_instance


def read_file_tool(
    filepath: str,
    offset: int = 1,
    limit: int = 500,
) -> dict:
    """Read a file with pagination support.

    Args:
        filepath: Path to the file to read
        offset: Line number to start from (1-indexed, default 1)
        limit: Maximum lines to return (default 500)

    Returns:
        Dictionary with file content or error
    """
    if _is_blocked_device_path(filepath):
        return {"error": f"Cannot read device path: {filepath}"}

    file_ops = _get_file_ops()
    result = file_ops.read_file(filepath, offset=offset, limit=limit)

    if result.error:
        return {"error": result.error}

    # Apply character limit
    content = result.content
    max_chars = _get_max_read_chars()
    if len(content) > max_chars:
        content = content[:max_chars]
        result.truncated = True
        result.hint = (
            f"Content truncated to {max_chars} characters. Use offset/limit for targeted reads."
        )

    return {
        "content": content,
        "total_lines": result.total_lines,
        "file_size": result.file_size,
        "truncated": result.truncated,
        "hint": result.hint,
    }


def write_file_tool(
    filepath: str,
    content: str,
) -> dict:
    """Write content to a file.

    Args:
        filepath: Path to the file to write
        content: Content to write

    Returns:
        Dictionary with success status or error
    """
    if _is_blocked_device_path(filepath):
        return {"error": f"Cannot write to device path: {filepath}"}

    file_ops = _get_file_ops()
    result = file_ops.write_file(filepath, content)

    if result.error:
        return {"error": result.error}

    return {
        "success": True,
        "bytes_written": result.bytes_written,
        "dirs_created": result.dirs_created,
    }


def list_files_tool(
    path: str = ".",
    pattern: str = "*",
    limit: int = 100,
) -> dict:
    """List files in a directory.

    Args:
        path: Directory path to list (default: current directory)
        pattern: File pattern to match (default: *)
        limit: Maximum number of files to return (default: 100)

    Returns:
        Dictionary with file list or error
    """
    try:
        import fnmatch

        if not os.path.exists(path):
            return {"error": f"Directory not found: {path}"}

        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}

        files = []
        for item in os.listdir(path):
            if fnmatch.fnmatch(item, pattern):
                item_path = os.path.join(path, item)
                stat = os.stat(item_path)
                files.append(
                    {
                        "name": item,
                        "path": item_path,
                        "size": stat.st_size,
                        "is_dir": os.path.isdir(item_path),
                        "modified": stat.st_mtime,
                    }
                )

        # Sort by name
        files.sort(key=lambda x: x["name"])

        # Apply limit
        if len(files) > limit:
            files = files[:limit]
            truncated = True
        else:
            truncated = False

        return {
            "files": files,
            "total": len(files),
            "truncated": truncated,
        }

    except OSError as e:
        return {"error": f"Failed to list directory: {e}"}


def delete_file_tool(
    filepath: str,
) -> dict:
    """Delete a file.

    Args:
        filepath: Path to the file to delete

    Returns:
        Dictionary with success status or error
    """
    if _is_blocked_device_path(filepath):
        return {"error": f"Cannot delete device path: {filepath}"}

    file_ops = _get_file_ops()
    result = file_ops.delete_file(filepath)

    if result.error:
        return {"error": result.error}

    return {"success": True}


def move_file_tool(
    src: str,
    dst: str,
) -> dict:
    """Move/rename a file.

    Args:
        src: Source file path
        dst: Destination file path

    Returns:
        Dictionary with success status or error
    """
    for path in (src, dst):
        if _is_blocked_device_path(path):
            return {"error": f"Cannot operate on device path: {path}"}

    file_ops = _get_file_ops()
    result = file_ops.move_file(src, dst)

    if result.error:
        return {"error": result.error}

    return {"success": True}


def search_files_tool(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    limit: int = 50,
) -> dict:
    """Search for content in files.

    Args:
        pattern: Search pattern (string to find)
        path: Directory to search in (default: current directory)
        file_pattern: File pattern to match (default: *)
        limit: Maximum number of matches to return (default: 50)

    Returns:
        Dictionary with search results or error
    """
    file_ops = _get_file_ops()
    result = file_ops.search(
        pattern=pattern,
        path=path,
        file_glob=file_pattern,
        limit=limit,
    )

    if result.error:
        return {"error": result.error}

    return {
        "matches": [
            {
                "path": m.path,
                "line": m.line_number,
                "content": m.content,
            }
            for m in result.matches
        ],
        "files": result.files,
        "counts": result.counts,
        "total_count": result.total_count,
        "truncated": result.truncated,
    }
