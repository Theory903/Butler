"""Forwarding stub — re-exports from the real hermes singularity environment."""

from integrations.hermes.tools.environments.singularity import *  # noqa: F401, F403
from integrations.hermes.tools.environments.singularity import (
    SingularityEnvironment,
    _get_scratch_dir,
)

__all__ = ["SingularityEnvironment", "_get_scratch_dir"]
