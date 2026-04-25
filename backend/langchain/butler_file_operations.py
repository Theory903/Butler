"""
Butler-native file operations module.

Provides file manipulation capabilities (read, write, search) that work
with Butler's sandbox infrastructure instead of Hermes terminal backends.
This is a Butler-native implementation that replaces Hermes file_operations.py
to avoid deep Hermes dependencies.
"""

import difflib
import os
from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Result Data Classes
# =============================================================================


@dataclass
class ReadResult:
    """Result from reading a file."""

    content: str = ""
    total_lines: int = 0
    file_size: int = 0
    truncated: bool = False
    hint: str | None = None
    is_binary: bool = False
    is_image: bool = False
    base64_content: str | None = None
    mime_type: str | None = None
    dimensions: str | None = None
    error: str | None = None
    similar_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != []}


@dataclass
class WriteResult:
    """Result from writing a file."""

    bytes_written: int = 0
    dirs_created: bool = False
    error: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PatchResult:
    """Result from patching a file."""

    success: bool = False
    diff: str = ""
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    lint: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        result = {"success": self.success}
        if self.diff:
            result["diff"] = self.diff
        if self.files_modified:
            result["files_modified"] = self.files_modified
        if self.files_created:
            result["files_created"] = self.files_created
        if self.files_deleted:
            result["files_deleted"] = self.files_deleted
        if self.lint:
            result["lint"] = self.lint
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class SearchMatch:
    """A single search match."""

    path: str
    line_number: int
    content: str
    mtime: float = 0.0


@dataclass
class SearchResult:
    """Result from searching."""

    matches: list[SearchMatch] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    total_count: int = 0
    truncated: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        result = {"total_count": self.total_count}
        if self.matches:
            result["matches"] = [
                {"path": m.path, "line": m.line_number, "content": m.content} for m in self.matches
            ]
        if self.files:
            result["files"] = self.files
        if self.counts:
            result["counts"] = self.counts
        if self.truncated:
            result["truncated"] = True
        if self.error:
            result["error"] = self.error
        return result


# =============================================================================
# Binary Extensions
# =============================================================================

# Common binary file extensions
BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".a",
    ".lib",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".rar",
    ".7z",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wav",
    ".flac",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".o",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".sqlite3",
}

# Image extensions (subset of binary that we can return as base64)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}


# =============================================================================
# Configuration Limits
# =============================================================================

MAX_LINES = 2000
MAX_LINE_LENGTH = 2000
MAX_FILE_SIZE = 50 * 1024  # 50KB
DEFAULT_READ_OFFSET = 1
DEFAULT_READ_LIMIT = 500


# =============================================================================
# Butler File Operations
# =============================================================================


class ButlerFileOperations:
    """
    Butler-native file operations.

    Uses Butler's sandbox infrastructure instead of Hermes terminal backends.
    Implements basic file safety checks inline to avoid Hermes dependencies.
    """

    def __init__(self, sandbox_manager=None):
        """
        Initialize Butler file operations.

        Args:
            sandbox_manager: Butler's sandbox manager for execution (optional)
        """
        self.sandbox_manager = sandbox_manager
        # Basic write deny list (can be extended with Butler policy later)
        self._write_denied_prefixes = [
            "/etc/",
            "/usr/",
            "/bin/",
            "/sbin/",
            "/sys/",
            "/proc/",
            "/boot/",
            "/root/",
        ]

    def _check_write_allowed(self, path: str) -> tuple[bool, str | None]:
        """Check if write operation is allowed by basic safety rules."""
        abs_path = os.path.abspath(path)
        for prefix in self._write_denied_prefixes:
            if abs_path.startswith(prefix):
                return False, f"Write denied: path in protected system directory ({prefix})"
        return True, None

    def _is_binary(self, path: str, content_sample: str = None) -> bool:
        """Check if a file is likely binary."""
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            return True

        # Content analysis: >30% non-printable chars = binary
        if content_sample:
            non_printable = sum(
                1 for c in content_sample[:1000] if ord(c) < 32 and c not in "\n\r\t"
            )
            return non_printable / min(len(content_sample), 1000) > 0.30

        return False

    def _is_image(self, path: str) -> bool:
        """Check if file is an image."""
        ext = os.path.splitext(path)[1].lower()
        return ext in IMAGE_EXTENSIONS

    def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
        """Add line numbers to content in LINE_NUM|CONTENT format."""
        lines = content.split("\n")
        numbered = []
        for i, line in enumerate(lines, start=start_line):
            # Truncate long lines
            if len(line) > MAX_LINE_LENGTH:
                line = line[:MAX_LINE_LENGTH] + "... [truncated]"
            numbered.append(f"{i:6d}|{line}")
        return "\n".join(numbered)

    def _unified_diff(self, old_content: str, new_content: str, filename: str) -> str:
        """Generate unified diff between old and new content."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}"
        )
        return "".join(diff)

    def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ReadResult:
        """
        Read a file with pagination, binary detection, and line numbers.

        Args:
            path: File path (absolute or relative to cwd)
            offset: Line number to start from (1-indexed, default 1)
            limit: Maximum lines to return (default 500, max 2000)

        Returns:
            ReadResult with content, metadata, or error info
        """
        # Normalize pagination
        offset = max(1, offset)
        limit = max(1, min(limit, MAX_LINES))

        # Check if file exists
        if not os.path.exists(path):
            return ReadResult(error=f"File not found: {path}")

        # Get file size
        try:
            file_size = os.path.getsize(path)
        except OSError:
            return ReadResult(error=f"Cannot access file: {path}")

        # Check if file is too large
        if file_size > MAX_FILE_SIZE:
            pass  # Still try to read, but could be slow

        # Images are never inlined
        if self._is_image(path):
            return ReadResult(
                is_image=True,
                is_binary=True,
                file_size=file_size,
                hint="Image file detected. Use vision tools to inspect.",
            )

        # Read a sample to check for binary content
        try:
            with open(path, "rb") as f:
                sample = f.read(1000).decode("utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return ReadResult(
                is_binary=True, file_size=file_size, error="Binary file - cannot display as text."
            )

        if self._is_binary(path, sample):
            return ReadResult(
                is_binary=True, file_size=file_size, error="Binary file - cannot display as text."
            )

        # Read full file
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return ReadResult(error=f"Failed to read file: {e}")

        # Get total line count
        lines = content.split("\n")
        total_lines = len(lines)

        # Paginate
        end_line = offset + limit - 1
        paginated_lines = lines[offset - 1 : end_line]
        paginated_content = "\n".join(paginated_lines)

        # Check if truncated
        truncated = total_lines > end_line
        hint = None
        if truncated:
            hint = f"Use offset={end_line + 1} to continue reading (showing {offset}-{end_line} of {total_lines} lines)"

        return ReadResult(
            content=self._add_line_numbers(paginated_content, offset),
            total_lines=total_lines,
            file_size=file_size,
            truncated=truncated,
            hint=hint,
        )

    def read_file_raw(self, path: str) -> ReadResult:
        """Read the complete file content as a plain string."""
        if not os.path.exists(path):
            return ReadResult(error=f"File not found: {path}")

        try:
            file_size = os.path.getsize(path)
        except OSError:
            return ReadResult(error=f"Cannot access file: {path}")

        if self._is_image(path):
            return ReadResult(is_image=True, is_binary=True, file_size=file_size)

        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            return ReadResult(error=f"Failed to read file: {e}")
        except UnicodeDecodeError:
            return ReadResult(
                is_binary=True, file_size=file_size, error="Binary file — cannot display as text."
            )

        return ReadResult(content=content, file_size=file_size)

    def write_file(self, path: str, content: str) -> WriteResult:
        """
        Write content to a file, creating parent directories as needed.

        Args:
            path: File path to write
            content: Content to write

        Returns:
            WriteResult with bytes written or error
        """
        # Check write policy
        allowed, reason = self._check_write_allowed(path)
        if not allowed:
            return WriteResult(error=f"Write denied: {reason}")

        # Create parent directories
        parent_dir = os.path.dirname(path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except OSError as e:
                return WriteResult(error=f"Failed to create directories: {e}")

        # Write file
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            bytes_written = len(content.encode("utf-8"))
            return WriteResult(bytes_written=bytes_written, dirs_created=bool(parent_dir))
        except OSError as e:
            return WriteResult(error=f"Failed to write file: {e}")

    def patch_replace(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> PatchResult:
        """Replace text in a file."""
        # Check write policy
        allowed, reason = self._check_write_allowed(path)
        if not allowed:
            return PatchResult(error=f"Write denied: {reason}")

        # Read current content
        read_result = self.read_file_raw(path)
        if read_result.error:
            return PatchResult(error=read_result.error)

        old_content = read_result.content

        # Perform replacement
        if replace_all:
            new_content = old_content.replace(old_string, new_string)
        else:
            new_content = old_content.replace(old_string, new_string, 1)

        # Generate diff
        diff = self._unified_diff(old_content, new_content, path)

        # Write new content
        write_result = self.write_file(path, new_content)
        if write_result.error:
            return PatchResult(error=write_result.error)

        return PatchResult(success=True, diff=diff, files_modified=[path])

    def delete_file(self, path: str) -> WriteResult:
        """Delete a file."""
        allowed, reason = self._check_write_allowed(path)
        if not allowed:
            return WriteResult(error=f"Delete denied: {reason}")

        try:
            os.remove(path)
            return WriteResult()
        except OSError as e:
            return WriteResult(error=f"Failed to delete {path}: {e}")

    def move_file(self, src: str, dst: str) -> WriteResult:
        """Move a file."""
        for p in (src, dst):
            allowed, reason = self._check_write_allowed(p)
            if not allowed:
                return WriteResult(error=f"Move denied: {reason}")

        try:
            os.rename(src, dst)
            return WriteResult()
        except OSError as e:
            return WriteResult(error=f"Failed to move {src} -> {dst}: {e}")

    def search(
        self,
        pattern: str,
        path: str = ".",
        target: str = "content",
        file_glob: str | None = None,
        limit: int = 50,
        offset: int = 0,
        output_mode: str = "content",
        context: int = 0,
    ) -> SearchResult:
        """Search for content or files."""
        matches: list[SearchMatch] = []
        files: list[str] = []
        counts: dict[str, int] = {}
        total_count = 0

        try:
            # Walk directory
            for root, _dirs, filenames in os.walk(path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)

                    # Apply glob filter if provided
                    if file_glob:
                        import fnmatch

                        if not fnmatch.fnmatch(filename, file_glob):
                            continue

                    # Search in file
                    try:
                        with open(file_path, encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if pattern.lower() in line.lower():
                                    matches.append(
                                        SearchMatch(
                                            path=file_path,
                                            line_number=line_num,
                                            content=line.strip(),
                                        )
                                    )
                                    counts[file_path] = counts.get(file_path, 0) + 1
                                    total_count += 1

                                    # Apply limit
                                    if total_count >= limit:
                                        break
                    except (OSError, UnicodeDecodeError):
                        pass

            files = list(counts.keys())

        except OSError as e:
            return SearchResult(error=f"Search failed: {e}")

        return SearchResult(
            matches=matches[offset : offset + limit],
            files=files,
            counts=counts,
            total_count=total_count,
            truncated=len(matches) > limit,
        )
