"""Butler-Hermes utility tools.

Utility functions from Hermes that have been assimilated into Butler.
These are low-risk tools that can be directly imported.
"""

import re
from typing import Any

import httpx


class ButlerHermesUtilityTools:
    """Butler-native utility tools from Hermes.

    Contains low-risk utility functions:
    - fuzzy_find_and_replace: Text matching and replacement
    - strip_ansi: ANSI escape sequence removal
    - is_safe_url: SSRF protection
    - check_package_for_malware: OSV malware check
    """

    @staticmethod
    async def fuzzy_find_and_replace(
        content: str,
        search: str,
        replace: str,
        *,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> dict[str, Any]:
        """Find and replace text using multiple strategies.

        Args:
            content: Content to search in
            search: Text to search for
            replace: Text to replace with
            case_sensitive: Whether search is case-sensitive
            use_regex: Whether to use regex matching

        Returns:
            Dictionary with new_content, match_count, strategy, error
        """
        if not content:
            return {
                "new_content": content,
                "match_count": 0,
                "strategy": "none",
                "error": "Empty content",
            }

        strategies = ["exact", "regex", "fuzzy"]
        for strategy in strategies:
            try:
                if strategy == "exact":
                    if use_regex:
                        continue
                    if case_sensitive:
                        new_content = content.replace(search, replace)
                        match_count = content.count(search)
                    else:
                        new_content = re.sub(
                            re.escape(search), replace, content, flags=re.IGNORECASE
                        )
                        match_count = len(re.findall(re.escape(search), content, re.IGNORECASE))

                elif strategy == "regex":
                    if not use_regex:
                        continue
                    flags = 0 if case_sensitive else re.IGNORECASE
                    new_content = re.sub(search, replace, content, flags=flags)
                    match_count = len(re.findall(search, content, flags=flags))

                elif strategy == "fuzzy":
                    # Simple fuzzy matching using substring
                    if use_regex:
                        continue
                    search_lower = search.lower() if not case_sensitive else search
                    content_lower = content.lower() if not case_sensitive else content

                    if search_lower in content_lower:
                        # Find all occurrences
                        matches = []
                        start = 0
                        while True:
                            idx = content_lower.find(search_lower, start)
                            if idx == -1:
                                break
                            matches.append(idx)
                            start = idx + 1

                        # Replace from end to preserve indices
                        new_content = content
                        for idx in reversed(matches):
                            new_content = (
                                new_content[:idx] + replace + new_content[idx + len(search) :]
                            )
                        match_count = len(matches)
                    else:
                        new_content = content
                        match_count = 0

                if match_count > 0:
                    return {
                        "new_content": new_content,
                        "match_count": match_count,
                        "strategy": strategy,
                        "error": None,
                    }

            except Exception:
                continue

        return {
            "new_content": content,
            "match_count": 0,
            "strategy": "none",
            "error": "No matches found",
        }

    @staticmethod
    def strip_ansi(text: str) -> str:
        """Remove ANSI escape sequences from text.

        Args:
            text: Text with ANSI escape sequences

        Returns:
            Text without ANSI escape sequences
        """
        # ANSI escape sequence pattern
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    @staticmethod
    def is_safe_url(url: str, allow_private: bool = False) -> bool:
        """Check if a URL is safe (SSRF protection).

        Args:
            url: URL to check
            allow_private: Whether to allow private network addresses

        Returns:
            True if URL is safe, False otherwise
        """
        import socket

        try:
            # Parse hostname
            if url.startswith("http://"):
                hostname = url[7:].split("/")[0].split(":")[0]
            elif url.startswith("https://"):
                hostname = url[8:].split("/")[0].split(":")[0]
            else:
                return False

            # Check for private IP addresses
            if not allow_private:
                try:
                    ip = socket.gethostbyname(hostname)
                    # Check for private IP ranges
                    private_ranges = [
                        ("10.0.0.0", "10.255.255.255"),
                        ("172.16.0.0", "172.31.255.255"),
                        ("192.168.0.0", "192.168.255.255"),
                        ("127.0.0.0", "127.255.255.255"),
                    ]
                    for start, end in private_ranges:
                        if ip >= start and ip <= end:
                            return False
                except socket.gaierror:
                    return False

            return True

        except Exception:
            return False

    @staticmethod
    async def check_package_for_malware(
        package_name: str, version: str | None = None
    ) -> dict[str, Any]:
        """Check a package for malware using OSV API.

        Args:
            package_name: Package name (e.g., "requests")
            version: Package version (optional)

        Returns:
            Dictionary with vulnerabilities found
        """
        try:
            # OSV API endpoint
            url = "https://api.osv.dev/v1/query"

            payload: dict[str, Any] = {"package": {"name": package_name, "ecosystem": "PyPI"}}
            if version:
                payload["version"] = version

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

            vulns = data.get("vulns", [])
            return {
                "package": package_name,
                "version": version,
                "vulnerabilities_found": len(vulns),
                "vulnerabilities": vulns[:10],  # Limit to first 10
                "safe": len(vulns) == 0,
            }

        except Exception as e:
            return {
                "package": package_name,
                "version": version,
                "vulnerabilities_found": 0,
                "vulnerabilities": [],
                "safe": False,
                "error": str(e),
            }
