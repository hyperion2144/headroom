"""OMP (Oh My Pi) provider helpers for wrap and persistent install.

Mirrors the ``headroom/providers/opencode/`` module structure.
"""

from .config import (
    _CONFIG_MARKER_END,
    _CONFIG_MARKER_START,
    omp_home_dir,
    omp_mcp_config_path,
    strip_omp_headroom_blocks,
)
from .runtime import build_launch_env, proxy_base_url

__all__ = [
    "_CONFIG_MARKER_END",
    "_CONFIG_MARKER_START",
    "build_launch_env",
    "omp_home_dir",
    "omp_mcp_config_path",
    "proxy_base_url",
    "strip_omp_headroom_blocks",
]
