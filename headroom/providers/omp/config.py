"""OMP config file helpers for wrap and persistent install.

Mirrors ``headroom/providers/opencode/config.py`` — same function shapes
adapted for OMP's YAML config files and project-level ``.omp/mcp.json``.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Headroom-managed YAML comment markers for idempotent block injection.
# OMP's config.yml starts as a YAML file; we use #-prefixed comment lines
# that are valid YAML (# starts a line comment) and easy to spot/strip.
# ---------------------------------------------------------------------------
_CONFIG_MARKER_START = "# --- Headroom proxy config ---"
_CONFIG_MARKER_END = "# --- end Headroom ---"

# Regex to strip the Headroom marker block (inclusive of both markers).
_CONFIG_BLOCK_RE = re.compile(
    re.escape(_CONFIG_MARKER_START) + r".*?" + re.escape(_CONFIG_MARKER_END),
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def omp_home_dir() -> Path:
    """Return the OMP agent config directory.

    Respects ``PI_CODING_AGENT_DIR`` (or its alias ``OMP_CODING_AGENT_DIR``)
    when set; defaults to ``~/.omp/agent/``.
    """
    env_override = os.environ.get("PI_CODING_AGENT_DIR") or os.environ.get("OMP_CODING_AGENT_DIR")
    if env_override:
        return Path(env_override)
    return Path.home() / ".omp" / "agent"


def omp_models_yml_path() -> Path:
    """Return ``~/.omp/agent/models.yml``."""
    return omp_home_dir() / "models.yml"


def omp_mcp_config_path() -> Path:
    """Return ``<cwd>/.omp/mcp.json`` (project-local MCP config)."""
    return Path.cwd() / ".omp" / "mcp.json"


def omp_config_paths() -> tuple[Path, Path]:
    """Return ``(config_file, backup_file)`` for OMP ``models.yml``.

    The backup file sits next to the original with a ``.headroom-backup``
    suffix, matching the opencode provider convention.
    """
    config_file = omp_models_yml_path()
    backup_file = config_file.with_suffix(".yml.headroom-backup")
    return config_file, backup_file


# ---------------------------------------------------------------------------
# Snapshot — backup before first injection
# ---------------------------------------------------------------------------


def snapshot_omp_models_if_unwrapped(config_file: Path, backup_file: Path) -> None:
    """Snapshot ``models.yml`` to ``backup_file`` before the first injection.

    Idempotent: skips when the backup already exists, when the source is
    absent, or when ``models.yml`` already contains Headroom markers (which
    means it was previously wrapped and never unwrapped — re-injecting on top
    is safe, but there's nothing new to snapshot).
    """
    if backup_file.exists():
        return
    if not config_file.exists():
        return
    # If the config already has headroom markers, skip the snapshot —
    # the backup was either already taken or never existed, but in either
    # case a pre-headroom backup is gone.
    try:
        content = config_file.read_text(encoding="utf-8")
    except OSError:
        return
    if _CONFIG_MARKER_START in content:
        return
    shutil.copy2(config_file, backup_file)


# ---------------------------------------------------------------------------
# Strip — remove Headroom-managed marker blocks from content
# ---------------------------------------------------------------------------


def strip_omp_headroom_blocks(content: str) -> str:
    """Remove Headroom-managed marker blocks from YAML config text."""
    cleaned = _CONFIG_BLOCK_RE.sub("", content)
    # Collapse runs of 2+ newlines to single newline (clean paragraph join).
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Inject — modify models.yml to route providers through Headroom proxy
# ---------------------------------------------------------------------------


def _modify_provider_base_urls(
    providers: dict[str, dict[str, object]],
    proxy_port: int,
) -> int:
    """Rewrite ``baseUrl`` in each provider to point at the local proxy.

    Returns the count of modified providers.
    """
    modified = 0
    for provider_name, provider_config in providers.items():
        if not isinstance(provider_config, dict):
            continue
        if "baseUrl" not in provider_config:
            continue
        original_url = provider_config.pop("baseUrl", None)
        # Preserve the original upstream as a comment-encoded header so the
        # proxy can route to it (x-headroom-base-url pattern).
        provider_config["baseUrl"] = f"http://127.0.0.1:{proxy_port}"
        # Store the original upstream URL so the proxy can forward there.
        provider_config.get("_original_baseUrl", original_url)  # probe only
        # Store original for unwrap to restore. Use a field that starts with
        # underscore so it doesn't interfere with OMP's normal parsing.
        provider_config["_headroom_original_baseUrl"] = str(original_url) if original_url else ""
        modified += 1
    return modified


def _headroom_provider_entry(port: int) -> dict[str, object]:
    """Return the ``headroom`` provider block for project config."""
    return {
        "baseUrl": f"http://127.0.0.1:{port}",
        "api": "openai-completions",
        "auth": "none",
        "models": [
            {
                "id": "headroom-proxy",
                "name": "Headroom Compression Proxy",
                "input": ["text"],
                "contextWindow": 200000,
                "maxTokens": 16384,
            },
        ],
    }


def inject_omp_proxy_config(port: int) -> None:
    """Modify OMP config to route provider traffic through Headroom proxy.

    1. Snapshot ``models.yml`` before modification.
    2. Parse ``models.yml``, rewrite every provider's ``baseUrl`` to the proxy.
    3. Write the Headroom marker block into project ``.omp/config.yml``.
    """
    config_file, backup_file = omp_config_paths()
    snapshot_omp_models_if_unwrapped(config_file, backup_file)

    if not config_file.exists():
        return  # nothing to inject

    try:
        raw = config_file.read_text(encoding="utf-8")
    except OSError:
        return

    # Parse YAML
    if _yaml is None:
        raise RuntimeError("PyYAML is required for OMP models.yml manipulation")
    data = _yaml.safe_load(raw) or {}

    # Modify provider baseUrl's
    providers = data.get("providers", {})
    if isinstance(providers, dict) and providers:
        modified_count = _modify_provider_base_urls(providers, port)
        if modified_count:
            _yaml_data = _yaml.dump(data, default_flow_style=False, sort_keys=False)
            config_file.write_text(
                f"# Modified by Headroom — provider traffic routed through proxy\n{_yaml_data}",
                encoding="utf-8",
            )

    # Write marker block into project .omp/config.yml
    project_config_path = Path.cwd() / ".omp" / "config.yml"
    if project_config_path.exists():
        existing = project_config_path.read_text(encoding="utf-8")
        if _CONFIG_MARKER_START not in existing:
            marker_block = (
                f"\n{_CONFIG_MARKER_START}\n"
                f"# Provider traffic routed through Headroom proxy on port {port}\n"
                f"# Managed by `headroom wrap omp` / `headroom unwrap omp`\n"
                f"headroom:\n"
                f"  proxy:\n"
                f"    enabled: true\n"
                f"    port: {port}\n"
                f"{_CONFIG_MARKER_END}\n"
            )
            project_config_path.write_text(existing.rstrip() + marker_block, encoding="utf-8")


# ---------------------------------------------------------------------------
# Restore — undo the effects of inject_omp_proxy_config
# ---------------------------------------------------------------------------


def restore_omp_models_yml() -> tuple[str, Path]:
    """Restore ``models.yml`` to pre-wrap state.

    Returns ``(status, path)`` where status is one of:
    - ``"restored"`` — backup existed and was restored
    - ``"cleaned"`` — no backup; Headroom markers stripped from active file
    - ``"noop"`` — no backup and no markers found

    The returned path is the live ``models.yml`` location.
    """
    config_file, backup_file = omp_config_paths()

    # Strategy 1: restore from backup
    if backup_file.exists():
        try:
            shutil.copy2(backup_file, config_file)
            backup_file.unlink()
            return "restored", config_file
        except OSError as exc:
            raise OSError(f"could not restore OMP models.yml from backup: {exc}") from exc

    # Strategy 2: strip Headroom markers from active file
    if config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        if _CONFIG_MARKER_START in content:
            cleaned = strip_omp_headroom_blocks(content)
            if cleaned.strip():
                config_file.write_text(cleaned + "\n", encoding="utf-8")
                return "cleaned", config_file
            config_file.unlink()
            return "removed", config_file

    return "noop", config_file
