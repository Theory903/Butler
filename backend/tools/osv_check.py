"""Forwarding stub — re-exports from integrations.hermes.tools.osv_check."""

try:
    from integrations.hermes.tools.osv_check import *  # noqa: F401, F403
    from integrations.hermes.tools.osv_check import check_package_for_malware

    __all__ = ["check_package_for_malware"]
except ImportError:
    pass
