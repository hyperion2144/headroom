"""OMP config file helpers for wrap and persistent install.

Mirrors ``headroom/providers/opencode/config.py`` — same function shapes
adapted for OMP's YAML config files and project-level ``.omp/mcp.json``.
"""

from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
from pathlib import Path

import click

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

# Environment variable the proxy reads to locate the upstream mapping file
# produced by ``inject_omp_proxy_config``. Keep in sync with c1/wrap.py which
# sets this when launching the proxy.
_HEADROOM_UPSTREAM_MAP_ENV = "HEADROOM_OMP_UPSTREAM_MAP"

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


def omp_upstream_map_path() -> Path:
    """Return ``<cwd>/.omp/.headroom-upstreams.json`` (project-local mapping).

    This file is the contract between ``inject_omp_proxy_config`` (producer)
    and the c3 ``OmpUpstreamRouterTransform`` (consumer): every concrete model
    id is mapped to the upstream ``baseUrl`` it should be routed to.
    """
    return Path.cwd() / ".omp" / ".headroom-upstreams.json"


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


def _strip_omp_config_markers(path: Path) -> str:
    """Strip Headroom-managed blocks from a project-local ``.omp/config.yml``.

    Mirrors the marker-strip logic in :func:`restore_omp_models_yml` for the
    project-local ``.omp/config.yml`` written by :func:`inject_omp_proxy_config`.
    Exposed here (rather than only in ``headroom/cli/wrap.py``) so future
    callers — programmatic unwrap, recovery scripts, tests — share one
    canonical implementation.

    Returns one of:

    - ``"stripped"`` — markers were present and stripped; non-empty content remains.
    - ``"removed"`` — the file contained only Headroom marker content; removed entirely.
    - ``"noop"`` — no markers found (or the file does not exist); file unchanged.
    """
    if not path.exists():
        return "noop"
    content = path.read_text(encoding="utf-8")
    if _CONFIG_MARKER_START not in content:
        return "noop"
    cleaned = strip_omp_headroom_blocks(content)
    if cleaned.strip():
        path.write_text(cleaned + "\n", encoding="utf-8")
        return "stripped"
    path.unlink()
    return "removed"


# ---------------------------------------------------------------------------
# Inject — modify models.yml to route providers through Headroom proxy
# ---------------------------------------------------------------------------


def _modify_provider_base_urls(
    providers: dict[str, dict[str, object]],
    proxy_port: int,
) -> int:
    """Rewrite ``baseUrl`` in each provider to point at the local proxy.

    Idempotent across re-wraps: if a provider already carries a truthy
    ``_headroom_original_baseUrl`` (i.e. it was wrapped previously), that
    value is preserved as the true original. The current ``baseUrl`` — which
    on a re-wrap is the proxy URL from the previous inject — is *not*
    captured as the original on a subsequent wrap.

    Returns the count of modified providers.
    """
    modified = 0
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    for provider_config in providers.values():
        if not isinstance(provider_config, dict):
            continue
        if "baseUrl" not in provider_config:
            continue
        # Preserve the true original across re-wraps: on a fresh wrap the
        # current baseUrl is the real upstream; on a re-wrap it is the proxy
        # URL from the previous inject — ignore that and keep the stored
        # true upstream.
        existing_original = provider_config.get("_headroom_original_baseUrl")
        if existing_original:
            original_url = existing_original
        else:
            original_url = provider_config.get("baseUrl")
        # Always (re)point the provider at the proxy.
        provider_config["baseUrl"] = proxy_url
        # Persist the true upstream under an underscore-prefixed field so it
        # is ignored by OMP but available to the proxy router and unwrap.
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
    3. Write the modified ``models.yml``.
    4. Build & persist the upstream mapping (``.omp/.headroom-upstreams.json``).
    5. Write the Headroom marker block into project ``.omp/config.yml``.
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
            # Build & persist the upstream mapping. ``_modify_provider_base_urls``
            # already populated ``_headroom_original_baseUrl`` on every touched
            # provider, so the builder sees a stable view. ``_write_upstream_map``
            # is called inside this block so an empty providers dict (zero
            # modifications) never produces a stale mapping file on disk.
            mapping = _build_upstream_map(data)
            _write_upstream_map(mapping)

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
# Upstream mapping — build & write ``.omp/.headroom-upstreams.json``
# ---------------------------------------------------------------------------


def _build_upstream_map(models_yml_data: dict) -> dict[str, str]:
    """Build ``{model_id: original_baseUrl}`` from parsed ``models.yml`` data.

    Iterates ``data["providers"]``; for each provider that is a dict and carries
    a truthy ``_headroom_original_baseUrl`` (i.e. was touched by
    ``_modify_provider_base_urls``), walks the provider's ``models`` list. Each
    model id — whether it appears as a bare string or as a dict with an ``id``
    key — is mapped to that provider's stored original ``baseUrl``.

    Skipped:
    - wildcard ids (``"*"``) — no upstream can be resolved for an unknown set
    - providers without a stored ``_headroom_original_baseUrl`` (e.g. those
      without a ``baseUrl`` to rewrite)
    - non-dict provider entries
    - empty or missing ``providers`` mapping

    Returns an empty dict when nothing maps; callers use that signal to skip
    writing the on-disk mapping file.
    """
    mapping: dict[str, str] = {}
    providers = models_yml_data.get("providers")
    if not isinstance(providers, dict) or not providers:
        return mapping
    for provider_config in providers.values():
        if not isinstance(provider_config, dict):
            continue
        original = provider_config.get("_headroom_original_baseUrl")
        if not original:
            continue
        original_url = str(original)
        models = provider_config.get("models")
        if not isinstance(models, list):
            continue
        for model in models:
            if isinstance(model, dict):
                model_id = model.get("id")
            elif isinstance(model, str):
                model_id = model
            else:
                continue
            if not model_id or model_id == "*":
                continue
            mapping[str(model_id)] = original_url
    return mapping


def _write_upstream_map(mapping: dict[str, str]) -> Path:
    """Write ``mapping`` as JSON to ``.omp/.headroom-upstreams.json``.

    Creates the ``.omp/`` parent directory if it does not yet exist. Keys are
    sorted and the file is indented for human inspection. Returns the path
    written so callers can record it in launch env or logs.
    """
    path = omp_upstream_map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _remove_upstream_map() -> None:
    """Delete ``.omp/.headroom-upstreams.json`` if present.

    Used by :func:`restore_omp_models_yml` so a stale upstream map does not
    outlive the wrap. Silent on missing file (``FileNotFoundError``) — an
    absent map is the expected state for a never-wrapped or already-cleaned
    project, and must not surface as an error during unwrap.
    """
    try:
        omp_upstream_map_path().unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Restore — undo the effects of inject_omp_proxy_config
# ---------------------------------------------------------------------------


def restore_omp_models_yml() -> tuple[str, Path]:
    """Restore ``models.yml`` to pre-wrap state.

    Returns ``(status, path)`` where status is one of:
    - ``"restored"`` — backup existed and was restored
    - ``"cleaned"`` — no backup; Headroom markers stripped from active file
    - ``"removed"`` — no backup; active file contained only Headroom content
    - ``"noop"`` — no backup and no markers found

    The returned path is the live ``models.yml`` location.

    Side effects:
    - When restoring from a backup whose contents differ from the live
      ``models.yml``, a non-blocking warning is emitted to stderr naming both
      files and noting local edits will be overwritten. The restore still
      proceeds.
    - On any non-noop restore (backup restored, markers stripped, or all-marker
      file removed) the project-local upstream mapping file
      (``.omp/.headroom-upstreams.json``) is deleted so it does not outlive the
      wrap. A missing mapping file is a silent no-op.
    """
    config_file, backup_file = omp_config_paths()

    status: str | None = None

    # Strategy 1: restore from backup
    if backup_file.exists():
        # Warn (non-blocking) when the live file diverged from the pre-wrap
        # backup. Skip the comparison if the live file is missing — there is
        # nothing to clobber in that case. A failed comparison (e.g. transient
        # permission error) must not block the restore either.
        if config_file.exists():
            try:
                if not filecmp.cmp(config_file, backup_file, shallow=False):
                    click.echo(
                        f"Warning: {config_file} differs from the pre-wrap "
                        f"backup ({backup_file}); local edits will be "
                        f"overwritten by the restore.",
                        err=True,
                    )
            except OSError:
                pass
        try:
            shutil.copy2(backup_file, config_file)
            backup_file.unlink()
        except OSError as exc:
            raise OSError(f"could not restore OMP models.yml from backup: {exc}") from exc
        status = "restored"
    # Strategy 2: strip Headroom markers from active file
    elif config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        if _CONFIG_MARKER_START in content:
            cleaned = strip_omp_headroom_blocks(content)
            if cleaned.strip():
                config_file.write_text(cleaned + "\n", encoding="utf-8")
                status = "cleaned"
            else:
                config_file.unlink()
                status = "removed"

    if status is None:
        # No backup and no markers: nothing was wrapped, so the filesystem must
        # remain untouched. This includes any pre-existing upstream mapping
        # file the user happens to have on disk.
        return "noop", config_file

    # Any actual restoration removes the upstream map so it does not outlive
    # the wrap. A missing file is expected and silently ignored.
    _remove_upstream_map()
    return status, config_file
