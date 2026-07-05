"""OMP config file helpers for wrap and persistent install.

Mirrors ``headroom/providers/opencode/config.py`` — same function shapes
adapted for OMP's YAML config files.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Headroom-managed YAML comment markers for idempotent block injection.
# OMP's config.yml starts as a YAML file; we use #-prefixed comment lines
# that are valid YAML (# starts a line comment) and easy to spot/strip.
# ---------------------------------------------------------------------------
_CONFIG_MARKER_START = "# --- Headroom proxy config ---"
_CONFIG_MARKER_END = "# --- end Headroom ---"

_CONFIG_BLOCK_RE = re.compile(
    re.escape(_CONFIG_MARKER_START) + r".*?" + re.escape(_CONFIG_MARKER_END),
    re.DOTALL,
)


def omp_home_dir() -> Path:
    """Return the OMP agent config directory.

    Respects ``PI_CODING_AGENT_DIR`` (or its alias ``OMP_CODING_AGENT_DIR``)
    when set.
    """
    env_override = os.environ.get("PI_CODING_AGENT_DIR") or os.environ.get("OMP_CODING_AGENT_DIR")
    return Path(env_override) if env_override else Path.home() / ".omp" / "agent"


def omp_mcp_config_path() -> Path:
    """Return ``~/.omp/agent/mcp.json`` (global OMP MCP config)."""
    return omp_home_dir() / "mcp.json"


def strip_omp_headroom_blocks(content: str) -> str:
    """Remove Headroom-managed marker blocks from YAML config text."""
    cleaned = _CONFIG_BLOCK_RE.sub("", content)
    # Collapse runs of 2+ newlines to single newline (clean paragraph join).
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()
