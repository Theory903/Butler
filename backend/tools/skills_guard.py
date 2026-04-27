"""Forwarding stub — re-exports from integrations.hermes.tools.skills_guard."""

try:
    from integrations.hermes.tools.skills_guard import *  # noqa: F401, F403
    from integrations.hermes.tools.skills_guard import (
        ScanResult,
        TRUSTED_REPOS,
        content_hash,
        format_scan_report,
        scan_skill,
        should_allow_install,
    )

    __all__ = [
        "ScanResult",
        "TRUSTED_REPOS",
        "content_hash",
        "format_scan_report",
        "scan_skill",
        "should_allow_install",
    ]
except ImportError:
    pass
