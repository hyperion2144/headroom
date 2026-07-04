"""OMP (Oh My Pi) provider helpers for wrap and persistent install.

Mirrors the ``headroom/providers/opencode/`` module structure. OMP uses YAML
config (``models.yml``) instead of JSON, and project-level ``.omp/mcp.json``
for MCP server registration, but the file-split and naming conventions match
the opencode provider exactly.
"""

from .config import (
    _CONFIG_MARKER_END,
    _CONFIG_MARKER_START,
    _HEADROOM_UPSTREAM_MAP_ENV,
    inject_omp_proxy_config,
    omp_config_paths,
    omp_home_dir,
    omp_mcp_config_path,
    omp_models_yml_path,
    omp_upstream_map_path,
    restore_omp_models_yml,
    snapshot_omp_models_if_unwrapped,
    strip_omp_headroom_blocks,
)
from .runtime import build_launch_env, proxy_base_url

__all__ = [
    "_CONFIG_MARKER_END",
    "_CONFIG_MARKER_START",
    "_HEADROOM_UPSTREAM_MAP_ENV",
    "build_launch_env",
    "inject_omp_proxy_config",
    "omp_config_paths",
    "omp_home_dir",
    "omp_mcp_config_path",
    "omp_models_yml_path",
    "omp_upstream_map_path",
    "proxy_base_url",
    "restore_omp_models_yml",
    "snapshot_omp_models_if_unwrapped",
    "strip_omp_headroom_blocks",
]
