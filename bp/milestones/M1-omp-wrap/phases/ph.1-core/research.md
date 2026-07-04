# Phase Research: ph.1-core — OMP Provider Module, MCP Registrar, CLI Stubs

> Implementation path investigation for OMP (Oh My Pi, v16.3.5) wrap integration core scaffolding.

---

## Research Scope

Research concrete implementation paths for creating the OMP provider module (`headroom/providers/omp/`), MCP registrar (`headroom/mcp_registry/omp.py`), and CLI stubs (`wrap omp`/`unwrap omp`). The phase creates the structural skeleton following the Opencode provider pattern, with complete implementations for config helpers, runtime env builders, and registrar — but CLI commands raise `NotImplementedError` (actual wiring in ph.2).

## Recommended Approach

**Recommendation**: Mirror `headroom/providers/opencode/` structure exactly, adapting for:
- YAML (PyYAML) vs JSON config format for `models.yml`
- `mcpServers` format (VSCode-style) for `.omp/mcp.json` vs OpenCode's `mcp` key
- Two config scopes: user-level `~/.omp/agent/models.yml` and project-level `.omp/mcp.json`/`.omp/config.yml`
- Per-provider `baseUrl` in-place modification (not new provider injection) for proxy routing

**Rationale**: The Opencode provider module is the closest existing analog — same CLI integration point, same MCP registratration pattern, same file-backup-idioms. Adapting it for OMP's YAML config format and `mcpServers` JSON format yields minimum delta from known-working patterns while correctly handling OMP's distinct file types.

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Single monolithic file** | Fewer files to create | Violates D1 (opencode pattern); harder to test; harder for maintainers to navigate | **Rejected** |
| **Separate directory per file (config/ subpackage)** | Clean boundaries | Over-engineered for 3-4 functions; no other provider does this | **Rejected** |
| **Inject new `headroom` provider rather than modify baseUrl** | Less invasive; easier to revert | OMP's routing doesn't support `headroom/` model prefix natively; would need model role changes | **Rejected** (per C2 in stack research) |
| **Plugin-based approach (OMP plugin install)** | Cleanest user experience | No documented OMP plugin/MCP-injection mechanism; spec requires `.omp/` file manipulation | **Rejected** |

## Detailed Path Research

### 1. `headroom/providers/omp/config.py` — Config Helpers

#### 1a. Path helpers

Three location types:

| Function | Path | Rationale |
|----------|------|-----------|
| `omp_home_dir()` | `Path.home() / ".omp" / "agent"` | OMP agent config root (`PI_CODING_AGENT_DIR` env var support) |
| `omp_models_yml_path()` | `omp_home_dir() / "models.yml"` | OMP provider model config |
| `omp_mcp_config_path()` | `Path.cwd() / ".omp" / "mcp.json"` | Project-level (per D4) |
| `omp_config_paths()` | `(models.yml, models.yml.with_suffix(".yml.headroom-backup"))` | Matches opencode `.json.headroom-backup` convention (D2) |

**Implementation detail**: `omp_home_dir()` should check `PI_CODING_AGENT_DIR` env var, same way `_opencode_home_dir()` checks `OPENCODE_HOME`.

```python
def omp_home_dir() -> Path:
    """Return the OMP user config directory (~/.omp/agent/)."""
    env_path = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".omp" / "agent"
```

#### 1b. Snapshot logic

`snapshot_omp_models_if_unwrapped(config_file, backup_file)`:
- Guard: if `backup_file.exists()` → return (idempotent)
- Guard: if not `config_file.exists()` → return (nothing to back up)
- Guard: if config contains Headroom markers → return (already wrapped, don't overwrite backup)
- Otherwise: `shutil.copy2(config_file, backup_file)`

Exactly mirrors `snapshot_opencode_config_if_unwrapped`. No new techniques needed.

#### 1c. Inject function

`inject_omp_proxy_config(port)` — this is the main wrap-time injection function. Per the interface contract it:
1. Modifies `models.yml` provider `baseUrl`s to proxy
2. Writes `.omp/mcp.json`
3. Marks `.omp/config.yml` with Headroom comment blocks

**For ph.1**: Full implementation is in scope — the CLI stubs don't call it, but the function should be implemented and testable. The non-goal of "models.yml actual modification at runtime" means the CLI won't invoke it, not that the function is stubbed.

**models.yml modification approach** (per C2 in stack research — in-place `baseUrl` change):
- Parse YAML with `yaml.safe_load()` 
- For each provider entry under `providers:`:
  - If the entry has a `baseUrl` key, rewrite it to `http://127.0.0.1:{port}/v1`
  - If no `baseUrl`, skip (emit warning)
- Write back via `yaml.dump(data, indent=2, sort_keys=False)` + leading comment markers
- **Pitfall**: `yaml.dump()` doesn't preserve ordering of `data` across Python dict versions (<3.7). Mitigation: Python 3.7+ preserves `dict` insertion order. The round-trip will lose comments but the backup ensures byte-for-byte recovery.

**YAML comment markers** (per D3):
```yaml
# --- Headroom proxy provider ---
providers:
  headroom:
    baseUrl: http://127.0.0.1:8787/v1
    ...
# --- end Headroom ---
```

But actually, the inject function is described as modifying existing providers' `baseUrl`s, not adding a new provider. The marker approach for `config.yml` is for project-level config marking. For models.yml, the primary safety net is the backup file, not markers.

**Revised understanding** — re-reading context.md:

```python
def inject_omp_proxy_config(port: int) -> None:
    """Modify models.yml provider baseUrl's to proxy; write .omp/mcp.json; mark .omp/config.yml."""
```

The function writes three things:
1. **models.yml**: In-place `baseUrl` rewrite for each provider (backup-first)
2. **.omp/mcp.json**: OMP MCP server entry via OmpRegistrar or direct write
3. **.omp/config.yml**: Marker-block injection for Headroom config metadata

For `.omp/config.yml`, create the file if absent with:
```yaml
# --- Headroom proxy config ---
headroom:
  proxy_port: {port}
  version: "1.0"
# --- end Headroom proxy config ---
```

#### 1d. Strip function

`strip_omp_headroom_blocks(content)`:
```python
_PROVIDER_MARKER_START = "# --- Headroom proxy provider ---"
_PROVIDER_MARKER_END = "# --- end Headroom ---"
_MCP_MARKER_START = "# --- Headroom MCP server ---"
_MCP_MARKER_END = "# --- end Headroom MCP server ---"
_CONFIG_MARKER_START = "# --- Headroom proxy config ---"
_CONFIG_MARKER_END = "# --- end Headroom proxy config ---"

_CONFIG_BLOCK_RE = re.compile(
    re.escape(_CONFIG_MARKER_START) + r".*?" + re.escape(_CONFIG_MARKER_END),
    re.DOTALL,
)

def strip_omp_headroom_blocks(content: str) -> str:
    content = _CONFIG_BLOCK_RE.sub("", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()
```

For models.yml, restoration uses the backup file (not markers). The strip function operates on `.omp/config.yml` YAML text.

#### 1e. Restore function

`restore_omp_models_yml()`:
- Check if backup exists → copy back, delete backup
- Otherwise → check if models.yml has markers → strip them
- Otherwise → no-op

### 2. `headroom/providers/omp/runtime.py` — Launch Environment

#### 2a. `proxy_base_url(port)`
```python
def proxy_base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"
```
Trivial, matches all other providers.

#### 2b. `build_launch_env(port, environ)`
Per KD-4 (architecture research), OMP gets configuration through file-based changes (models.yml + .omp/config.yml + .omp/mcp.json), so the launch env is minimal:
```python
def build_launch_env(
    port: int,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    env = dict(environ or os.environ)
    display = []
    
    # Inform OMP of the proxy URL (used by headroom server MCP)
    env["HEADROOM_PROXY_URL"] = f"http://127.0.0.1:{port}"
    display.append("HEADROOM_PROXY_URL=http://127.0.0.1:{port}")
    
    return env, display
```

Unlike Opencode (which needs `OPENCODE_CONFIG_CONTENT` for inline config, `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` for fallback routing, and transport plugin path), OMP is configured entirely through file modifications. The only runtime env var is `HEADROOM_PROXY_URL` for the headroom MCP server.

**No context-tool (rtk/lean-ctx) support** per KD-5 — OMP context compression is handled entirely through the proxy.

### 3. `headroom/mcp_registry/omp.py` — OmpRegistrar

#### 3a. Class structure

Follows `OpencodeRegistrar` pattern exactly, but reads/writes `.omp/mcp.json` in `mcpServers` key format (VSCode/Cursor/OMP style, not OpenCode's `mcp` key):

```python
class OmpRegistrar(MCPRegistrar):
    """Register MCP servers with OMP (.omp/mcp.json)."""
    
    name = "omp"
    display_name = "OMP"
    
    def __init__(self, *, config_path: Path | None = None) -> None:
        self._config_path = config_path or Path.cwd() / ".omp" / "mcp.json"
```

#### 3b. `detect()`
```python
def detect(self) -> bool:
    if shutil.which("omp"):
        return True
    return (Path.cwd() / ".omp").is_dir()
```
Two checks: `omp` binary in PATH (primary), or `.omp/` directory exists (project-level config present).

#### 3c. MCP JSON format for `.omp/mcp.json`

OMP uses this format (confirmed from `~/.omp/agent/mcp.json`):
```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "disabledServers": [...],
  "mcpServers": {
    "headroom": {
      "command": "headroom",
      "args": ["mcp", "serve"],
      "env": {}
    }
  }
}
```

Key differences from OpenCode's `mcp` key inside `opencode.json`:
- Uses `mcpServers` top-level key (not `mcp`)
- Each entry has `command`, `args`, `env` fields (not OpenCode's array-based format)
- Has optional `$schema` and `disabledServers` top-level keys
- JSON-only (no comment support needed — OMP's parser strips them)

#### 3d. `register_server()`

Strategy: read `.omp/mcp.json`, modify `data["mcpServers"][spec.name]`, write back:
```python
def register_server(self, spec: ServerSpec, *, force: bool = False) -> RegisterResult:
    if not force and self.get_server(spec.name) is not None:
        existing = self.get_server(spec.name)
        if _specs_equivalent(existing, spec):
            return RegisterResult(RegisterStatus.ALREADY, ...)
        return RegisterResult(RegisterStatus.MISMATCH, ...)
    
    try:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_json(self._config_path)
        mcp_servers = data.setdefault("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            mcp_servers = {}
            data["mcpServers"] = mcp_servers
        mcp_servers[spec.name] = {
            "command": spec.command,
            "args": list(spec.args) if spec.args else [],
        }
        if spec.env:
            mcp_servers[spec.name]["env"] = dict(spec.env)
        _write_json(self._config_path, data)
    except OSError as exc:
        return RegisterResult(RegisterStatus.FAILED, str(exc))
    return RegisterResult(RegisterStatus.REGISTERED, f"wrote to {self._config_path}")
```

`_read_json`/`_write_json` helpers match the existing pattern in `opencode.py` but operate on the `mcpServers` key.

#### 3e. `unregister_server()`
```python
def unregister_server(self, server_name: str) -> bool:
    data = _read_json(self._config_path)
    mcp_servers = data.get("mcpServers", {})
    if not isinstance(mcp_servers, dict) or server_name not in mcp_servers:
        return False
    del mcp_servers[server_name]
    if not mcp_servers:
        data.pop("mcpServers", None)
    try:
        _write_json(self._config_path, data)
    except OSError:
        return False
    return True
```

### 4. CLI Stubs (`headroom/cli/wrap.py` additions)

#### 4a. `wrap omp` command

Place registration at the end of existing `wrap` command group (after opencode at ~line 5600). Uses the same Click decorator pattern as other wrap subcommands:

```python
@wrap.command(context_settings={"ignore_unknown_options": True})
@click.option("--port", "-p", default=8787, type=click.IntRange(1, 65535), help="Proxy port (default: 8787)")
@click.option("--no-mcp", is_flag=True, help="Skip headroom MCP server registration")
@click.option("--no-proxy", is_flag=True, help="Skip proxy startup (use existing proxy)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--prepare-only", is_flag=True, hidden=True)
@click.argument("omp_args", nargs=-1, type=click.UNPROCESSED)
def omp(port, no_mcp, no_proxy, verbose, prepare_only, omp_args):
    """Launch OMP through Headroom proxy. [NOT YET IMPLEMENTED]"""
    raise NotImplementedError(
        "`headroom wrap omp` is not yet implemented. "
        "Use `headroom wrap` with other agents (opencode, claude, codex) in the meantime. "
        "See ph.2 for the full wrap implementation."
    )
```

**Key difference from `wrap opencode`**: Simpler option set — no `--no-rtk` (OMP doesn't use context-tool), no `--no-serena` (KD-5), no `--code-graph`, no `--learn`/`--memory` (not in scope for initial wrap), no `--backend`/`--anyllm-provider`/`--region`. Can be extended in ph.2.

#### 4b. `unwrap omp` command

```python
@unwrap.command("omp")
@click.option("--port", "-p", default=8787, type=click.IntRange(1, 65535), help="Proxy port (default: 8787)")
@click.option("--no-stop-proxy", is_flag=True, help="Do not stop the local Headroom proxy")
def unwrap_omp(port, no_stop_proxy):
    """Undo ``headroom wrap omp`` edits. [NOT YET IMPLEMENTED]"""
    raise NotImplementedError(
        "`headroom unwrap omp` is not yet implemented. "
        "See ph.2 for the full unwrap implementation."
    )
```

#### 4c. Import additions in wrap.py

Add at the top imports area (after `from headroom.providers.opencode import ...` at ~line 118):
```python
from headroom.providers.omp import build_launch_env as _build_omp_launch_env
from headroom.providers.omp.config import (
    inject_omp_proxy_config,
    omp_models_yml_path,
    snapshot_omp_models_if_unwrapped,
    strip_omp_headroom_blocks,
)
```

These imports are forward-looking (used in ph.2) but harmless in ph.1 — the stubs don't reference them.

### 5. `headroom/providers/omp/__init__.py` — Exports

Mirrors `headroom/providers/opencode/__init__.py`:

```python
from .config import (
    _CONFIG_MARKER_END,
    _CONFIG_MARKER_START,
    inject_omp_proxy_config,
    omp_config_paths,
    omp_home_dir,
    omp_mcp_config_path,
    omp_models_yml_path,
    snapshot_omp_models_if_unwrapped,
    strip_omp_headroom_blocks,
)
from .runtime import build_launch_env, proxy_base_url

__all__ = [
    "_CONFIG_MARKER_END",
    "_CONFIG_MARKER_START",
    "build_launch_env",
    "inject_omp_proxy_config",
    "omp_config_paths",
    "omp_home_dir",
    "omp_mcp_config_path",
    "omp_models_yml_path",
    "proxy_base_url",
    "snapshot_omp_models_if_unwrapped",
    "strip_omp_headroom_blocks",
]
```

## Known Pitfalls

- **P1 — YAML round-trip loses comments**: `yaml.dump(yaml.safe_load(content))` strips all YAML comments, key ordering shifts, and inline block scalars may reformat. **Mitigation**: (a) backup-first strategy guarantees byte-for-byte recovery; (b) for `models.yml`, only targeted `baseUrl` regex replacement (rather than full parse→dump) is safer — but only backup recovery provides guaranteed fidelity. Use `yaml.safe_load`/`yaml.dump` with `sort_keys=False` for the structured `config.yml` where we own the content.

- **P2 — `mcpServers` vs `mcp` confusion**: OMP uses `mcpServers` key in `.omp/mcp.json` while OpenCode uses `mcp` key in `opencode.json`. Importing `OmpRegistrar` into the `get_all_registrars()` list in `install.py` would require OmpRegistrar to handle the `mcpServers` key correctly — it already does, but the `install_everywhere` path only fires for `headroom install` (separate from wrap). Not an issue for ph.1.

- **P3 — Missing `~/.omp/agent/` directory**: If OMP isn't installed, `omp_home_dir()` returns a valid path but the directory may not exist. All snapshot/inject/restore functions must guard with `config_file.exists()` before reading.

- **P4 — `.omp/config.yml` doesn't exist initially**: The inject function must create the project `.omp/` directory and config file as needed, matching the `config_dir.mkdir(parents=True, exist_ok=True)` pattern from opencode.

- **P5 — `mcp.json` `$schema` field preservation**: OMP's `mcp.json` has a `$schema` URL at the top. The registrar must read the full JSON, modify only `mcpServers`, and write back — never strip the `$schema` or `disabledServers` fields.

- **P6 — OMP binary detection**: `shutil.which("omp")` finds the `omp` v16.3.5 binary at `~/.bun/bin/omp` in the user's environment. The `detect()` method should check both the binary and the `.omp/` directory to handle both installed-and-configured and configured-without-binary states.

- **P7 — `--verbose` output consistency**: The opencode wrap command uses `click.echo("  ...")` for status lines. OMP stubs should follow the same formatting for future consistency.

## TDD Implications

This phase is scaffolding, so TDD is minimal but not absent:

| Module | Test Strategy |
|--------|--------------|
| `config.py` | Unit-test path helpers (`omp_home_dir`, `omp_models_yml_path`, `omp_mcp_config_path`). Test `snapshot_omp_models_if_unwrapped` with temp files (idempotent). Test `strip_omp_headroom_blocks` with known YAML text. Test `restore_omp_models_yml` with backup present vs absent. |
| `runtime.py` | Unit-test `proxy_base_url` returns correct format. Test `build_launch_env` returns correct env dict. |
| `mcp_registry/omp.py` | Unit-test `OmpRegistrar` with temp `.omp/mcp.json`: `register_server` adds entry, `unregister_server` removes entry, `detect` returns True/False appropriately. Test `_specs_equivalent` helper. |
| `cli/wrap.py` | Test that `headroom wrap omp --help` prints help. Test that `headroom wrap omp` raises NotImplementedError. Test that `headroom unwrap omp --help` prints help. Test that `headroom unwrap omp` raises NotImplementedError. |

**Non-TDD**: Type annotations are sufficient typing for config.py/runtime.py stubs — no runtime type checks needed. The CLI stubs are trivial enough that only exit-code testing is warranted.
