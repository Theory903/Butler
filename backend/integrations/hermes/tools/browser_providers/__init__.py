"""Cloud browser provider abstraction.

Import the ABC so callers can do::

    from integrations.hermes.tools.browser_providers import CloudBrowserProvider
"""

from integrations.hermes.tools.browser_providers.base import CloudBrowserProvider

__all__ = ["CloudBrowserProvider"]
