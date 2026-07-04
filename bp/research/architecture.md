# Architecture Research: OMP Wrap

> Research output for OMP (Oh My Pi) integration into Headroom.
> Recommends module structure, architecture approach, and implementation plan with evaluated alternatives.

---

## Recommendation

**Hybrid structured + backup-based approach** — each OMP configuration file gets the optimal treatment per its file type and location, following the most closely matching existing Headroom pattern. Backup-first for user-global files (`~/.omp/agent/models.yml`); structured JSON manipulation for `.omp/mcp.json`; backup-first with marker fallback for `.omp/config.yml`.

## Architecture Overview

```
headroom wrap omp
├── _ensure_proxy(port)          # Start Headroom proxy (shared)
├── Backup models.yml
├── Inject proxy baseUrl into models.yml  # Route OMP's provider -> proxy
├── OmpRegistrar.register_server("headroom")  # -> .omp/mcp.json
├── Write config marker to .omp/config.yml
└── _launch_tool(binary="omp")   # Launch omp CLI

headroom unwrap omp
├── Restore ~/.omp/agent/models.yml from backup
│   └── (fallback: direct YAML key revert)
├── OmpRegistrar.unregister_server("headroom")  # -> .omp/mcp.json
├── Restore .omp/config.yml from backup
│   └── (fallback: strip Headroom markers)
└── Stop proxy (unless --no-stop-proxy)
```

### Module Dependency Graph

```
wrap.py  ──>  headroom.providers.omp
                  ├── __init__.py  (re-exports)
                  ├── config.py   (.omp/mcp.json, models.yml, .omp/config.yml)
                  └── runtime.py  (build_launch_env, proxy_base_url)
         ──>  headroom.mcp_registry.omp
                  └── OmpRegistrar (MCPRegistrar subclass)
```

---

## Alternatives Evaluated

| Approach | Strengths | Weaknesses | Verdict |
|----------|-----------|-----------|---------|
| **Marker-based** (all files use comment markers to delimit Headroom blocks) | Consistent with OpenCode/Codex patterns; unwrap works without backup | YAML comment markers inside structured config can be fragile; JSON encodings unstable; backup not used for models.yml (user-global, needs atomic restore) | **Rejected** — Over-abstracts the problem; OMP's file types need different treatments |
| **Structured + backup (recommended)** | Each file gets the optimal approach per its type; maximum safety for user-global file; consistent with existing registrar pattern for MCP | Slightly more sub-modules to maintain | **Selected** — Balances robustness and codebase consistency |
| **Plugin-based** (install an OMP plugin into OMP's plugin system) | Cleanest user experience; OMP-native | OMP has no documented plugin/MCP-injection mechanism; adds discovery overhead | **Rejected** — Spec requires `.omp/` file manipulation, not plugin architecture |

---

## Key Decisions

### KD-1: Models.yml backup-first (matching Codex pattern)

**File**: `~/.omp/agent/models.yml`

The user-local provider config is the most critical file to restore correctly. Full file copy (`models.yml.headroom-backup`) before modification, atomic restore on unwrap. Fallback: direct YAML manipulation to revert changed `baseUrl` keys if backup is missing.

This mirrors the Codex TOML backup approach in `headroom/providers/codex/config.py` and `CodexRegistrar`.

### KD-2: OmpRegistrar structured (matching MCPRegistrar pattern)

**File**: `.omp/mcp.json`

The `.omp/mcp.json` is a structured JSON file with an array of MCP server entries. Use `OmpRegistrar(MCPRegistrar)` following the `ClaudeRegistrar` / `OpencodeRegistrar` pattern: read JSON, add/remove headroom entry, write back. Backup on first mutation.

Expected MCP entry format to register:
```json
{
  "headroom": {
    "command": "headroom",
    "args": ["mcp", "serve"],
    "env": {}
  }
}
```

### KD-3: Config.yml backup-first with marker fallback

**File**: `.omp/config.yml`

Project-local YAML config. Backup on first wrap; restore from backup on unwrap. Without backup, search for `# --- Headroom ...` markers and strip the block. Markers ensure unwrap can find and remove Headroom content even when the backup file is manually deleted.

This mirrors the OpenCode pattern: `_PROVIDER_MARKER_START` / `_PROVIDER_MARKER_END` with a regex-based strip function.

### KD-4: Launch environment via `build_launch_env`

OMP is launched as a child process via `_launch_tool()` (shared helper from wrap.py). The `build_launch_env(port, environ)` function provides:
- `HEADROOM_PROXY_URL=http://127.0.0.1:{port}` — informs OMP of the proxy
- Existing `PATH` and env vars preserved

Unlike OpenCode (which uses `OPENCODE_CONFIG_CONTENT` to carry inline config), OMP gets configuration through file-based changes (models.yml + .omp/config.yml + .omp/mcp.json). The launch env is minimal — just `HEADROOM_PROXY_URL`.

### KD-5: No context-tool (rtk/lean-ctx) support for OMP

The spec does not call for rtk integration. OMP context compression is handled entirely through the proxy (same binary compressors). This simplifies the wrap command significantly compared to OpenCode/Claude wrap.

---

## Module Structure

### `headroom/providers/omp/__init__.py`

Re-exports from config.py and runtime.py following the OpenCode provider pattern:

```python
from .config import (
    inject_omp_provider_config,
    omp_project_paths,
    restore_omp_provider_config,
    snapshot_omp_config_if_unwrapped,
    snapshot_omp_models_if_unwrapped,
    strip_omp_config_markers,
)
from .runtime import build_launch_env, proxy_base_url

__all__ = [
    "build_launch_env",
    "inject_omp_provider_config",
    "omp_project_paths",
    "proxy_base_url",
    "restore_omp_provider_config",
    "snapshot_omp_config_if_unwrapped",
    "snapshot_omp_models_if_unwrapped",
    "strip_omp_config_markers",
]
```

### `headroom/providers/omp/config.py`

Core config manipulation functions for OMP's three configuration touchpoints.

```
Constants:
  _OMP_CONFIG_MARKER_START = "# --- Headroom proxy config ---"
  _OMP_CONFIG_MARKER_END   = "# --- end Headroom proxy config ---"
  HEADROOM_OMP_MODELS       # default proxy model entry
  _OMP_CONFIG_BACKUP_SUFFIX = ".headroom-backup"

Functions:
  omp_project_dir() -> Path
    Walk up from cwd to find .omp/ directory. Returns Path.cwd() / ".omp" by default.

  omp_mcp_json_path() -> Path
    omp_project_dir() / "mcp.json"

  omp_config_yml_path() -> Path
    omp_project_dir() / "config.yml"

  omp_models_yml_path() -> Path
    Path.home() / ".omp" / "agent" / "models.yml"

  omp_project_paths() -> tuple[Path, Path, Path]
    Returns (mcp_json, config_yml, models_yml).

  omp_backup_paths() -> tuple[Path, Path, Path]
    Returns backup paths for each config file.

  snapshot_omp_models_if_unwrapped(models_file, backup_file) -> None
    Copy ~/.omp/agent/models.yml to ~/.omp/agent/models.yml.headroom-backup
    if backup does not already exist and models.yml is present.
    Idempotent: does not overwrite existing backup.

  snapshot_omp_config_if_unwrapped(config_file, backup_file) -> None
    Copy .omp/config.yml to .omp/config.yml.headroom-backup if backup absent.
    Idempotent.

  inject_omp_provider_config(port) -> None
    Read ~/.omp/agent/models.yml, change all provider baseUrl entries
    to http://127.0.0.1:{port}/v1. Write back.
    Handles multiple provider formats (openai-base, anthropic-base, etc.).

  restore_omp_provider_config() -> str
    Restore ~/.omp/agent/models.yml from backup.
    Returns "restored", "cleaned", or "noop".

  inject_omp_config_marker(port) -> None
    Write Headroom config block (between markers) into .omp/config.yml.
    Idempotent: replaces existing marker block if present.

  strip_omp_config_markers(content) -> str
    Regex-remove the marker-delimited Headroom block from .omp/config.yml text.
```

### `headroom/providers/omp/runtime.py`

```python
def proxy_base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"

def build_launch_env(
    port: int,
    environ: Mapping[str, str] | None = None,
    *,
    project: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Build environment for launching OMP through Headroom."""
    env = dict(environ or os.environ)
    env["HEADROOM_PROXY_URL"] = f"http://127.0.0.1:{port}"
    display = ["HEADROOM_PROXY_URL=http://127.0.0.1:{port}"]
    if project and "HEADROOM_PROJECT" not in env:
        env["HEADROOM_PROJECT"] = project
    return env, display
```

### `headroom/mcp_registry/omp.py`

```python
class OmpRegistrar(MCPRegistrar):
    """Register MCP servers with OMP via .omp/mcp.json."""

    server_type = "omp"

    def __init__(self, project_dir: str | Path | None = None) -> None:
        self._project_dir = Path(project_dir or Path.cwd())
        self._mcp_json = self._project_dir / ".omp" / "mcp.json"

    def detect(self) -> bool:
        """Return True when .omp/mcp.json is writable."""
        return self._mcp_json.parent.is_dir()

    def registered_servers(self) -> dict[str, ServerSpec]:
        """Read current MCP servers from .omp/mcp.json."""
        ...

    def register_server(self, spec: ServerSpec) -> RegisterResult:
        """Add/update headroom entry in .omp/mcp.json."""
        ...

    def unregister_server(self, name: str) -> bool:
        """Remove named server from .omp/mcp.json."""
        ...
```

### `headroom/cli/wrap.py` additions

**wrap command** (following OpenCode pattern):

```python
@wrap.command(context_settings={"ignore_unknown_options": True})
@click.option("--port", "-p", default=8787, ...)
@click.option("--no-mcp", is_flag=True, help="Skip headroom MCP server registration")
@click.option("--no-proxy", is_flag=True, help="Skip proxy startup (use existing proxy)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--prepare-only", is_flag=True, hidden=True)
@click.argument("omp_args", nargs=-1, type=click.UNPROCESSED)
def omp(port, no_mcp, no_proxy, verbose, prepare_only, omp_args):
    """Launch OMP through Headroom proxy.
    ...
    """
    # Snapshot OMP configs
    snapshot_omp_models_if_unwrapped(...)
    snapshot_omp_config_if_unwrapped(...)

    # Register headroom MCP server
    if not no_mcp:
        _setup_headroom_mcp(OmpRegistrar(), port, verbose=verbose, force=True)

    # Inject models.yml proxy routing
    inject_omp_provider_config(port)

    # Inject config marker
    inject_omp_config_marker(port)

    if prepare_only:
        return

    omp_bin = shutil.which("omp")
    if not omp_bin:
        click.echo("Error: 'omp' not found in PATH.")
        raise SystemExit(1)

    env, display = _build_omp_launch_env(port, os.environ)
    _launch_tool(binary=omp_bin, args=omp_args, env=env, port=port,
                 no_proxy=no_proxy, tool_label="OMP", ...)
```

**unwrap command** (following OpenCode unwrap pattern):

```python
@unwrap.command("omp")
@click.option("--port", "-p", default=8787, ...)
@click.option("--no-stop-proxy", is_flag=True, ...)
def unwrap_omp(port, no_stop_proxy):
    """Undo ``headroom wrap omp`` edits.
    ...
    """
    # 1. Restore models.yml from backup (or revert baseUrl changes)
    restore_omp_provider_config()

    # 2. Remove headroom MCP from .omp/mcp.json
    registrar = OmpRegistrar()
    registrar.unregister_server("headroom")

    # 3. Restore config.yml from backup (or strip markers)
    ... (backup restore, else marker strip)

    # 4. Stop proxy unless --no-stop-proxy
    ...
```

### wrap.py imports to add

```python
from headroom.providers.omp import build_launch_env as _build_omp_launch_env
from headroom.providers.omp.config import (
    inject_omp_provider_config,
    omp_project_paths,
    restore_omp_provider_config,
    snapshot_omp_config_if_unwrapped,
    snapshot_omp_models_if_unwrapped,
    strip_omp_config_markers,
)
```

**AGENT_SAVINGS_TARGET_AGENTS** update — add `"omp"` to the tuple in wrap.py.

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| `.omp/mcp.json` format unknown (SPEC_GAP) | Wrong MCP entry shape | Medium | Implement with flexible JSON merge; verify against real `.omp/mcp.json` spec |
| `~/.omp/agent/models.yml` YAML format variation | Failed model injection | Low | Use safe YAML parser (ruamel.yaml); test with multi-provider models.yml |
| No `.omp/` directory exists at wrap time | Command fails | Low | Create `.omp/` dir if absent; `_ensure_proxy` handles gracefully |
| OMP version changes config format | Future incompatibility | Low | Backup-first strategy handles arbitrary changes; markers provide a safety net |
| Backup file left behind on crash | Stale files | Low | Unwrap always cleans up; `--prepare-only` leaves backup in known state |
| `.omp/config.yml` user edits after wrap | Marker strip loses user edits between markers | Low | Only the marker-delimited block is stripped; user content outside markers preserved |

---

## SPEC_GAP Items

The following gaps were identified in `bp/specs/omp/spec.md` and require clarification:

1. **`.omp/mcp.json` MCP entry format** — Spec references registering a Headroom MCP server but does not define the expected entry structure (command, args, env). Need to confirm: `{"command": "headroom", "args": ["mcp", "serve"], "env": {}}`.

2. **Models.yml provider key format** — Spec says "modify `baseUrl`", but models.yml may have multiple provider blocks (`openai`, `anthropic`, `openai-compatible`, etc.). Need to confirm which top-level keys we redirect and whether the URL rewrite is `provider.{name}.baseUrl` or a different nesting.

3. **`.omp/config.yml` schema** — Spec says "write Headroom config" but does not specify the YAML key structure (top-level list? object?). Need to confirm the expected config marker shape.

4. **Backup file naming** — Spec mentions `models.yml.headroom-backup` but does not define backup naming for `.omp/config.yml` and `.omp/mcp.json`. Recommend consistent `.headroom-backup` suffix for all files.

5. **Proxy port propagation** — Need to confirm OMP reads a specific env var for proxy URL (e.g., `HEADROOM_PROXY_URL`, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`) or if only models.yml rewriting is sufficient.

---

## Implementation Plan

### Phase 1: Provider module (2-3 PRs)

| Step | File | Description |
|------|------|-------------|
| 1 | `headroom/providers/omp/config.py` | Write config path helpers, backup functions, models.yml injection/restoration, marker helpers |
| 2 | `headroom/providers/omp/runtime.py` | Write `proxy_base_url()` and `build_launch_env()` |
| 3 | `headroom/providers/omp/__init__.py` | Re-export public API |
| 4 | `headroom/mcp_registry/omp.py` | Write `OmpRegistrar` subclass |

### Phase 2: CLI integration (1 PR)

| Step | File | Description |
|------|------|-------------|
| 5 | `headroom/cli/wrap.py` | Add `wrap omp` command, `unwrap omp` command, import provider module |
| 6 | `headroom/mcp_registry/__init__.py` | Add `OmpRegistrar` to exports and `get_all_registrars()` |
| 7 | Integration test | Manual wrap/unwrap cycle with real OMP project |
