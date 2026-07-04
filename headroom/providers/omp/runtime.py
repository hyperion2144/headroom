"""Runtime helpers for OMP integrations.

Intentionally smaller than the opencode provider's ``runtime.py`` — OMP
reads its configuration from on-disk files (``.omp/config.yml``, ``models.yml``)
rather than from environment-variable config blobs, so the launch environment
only needs to declare the proxy address.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


def proxy_base_url(port: int) -> str:
    """Return the local proxy base URL used by OMP integrations."""
    return f"http://127.0.0.1:{port}/v1"


def build_launch_env(
    port: int,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Build environment variables for launching OMP through Headroom.

    Sets ``HEADROOM_PROXY_URL`` so any OMP child process or plugin knows
    where the proxy is. Preserves all existing environment variables.

    Returns ``(env_dict, display_lines)``.
    """
    env = dict(environ or os.environ)

    env["HEADROOM_PROXY_URL"] = f"http://127.0.0.1:{port}"

    display: list[Any] = [f"HEADROOM_PROXY_URL=http://127.0.0.1:{port}"]

    return env, display
