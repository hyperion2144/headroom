# Design: c1-provider-module

> This document is the Change Design — written after proposal approval, describing how to implement the OMP provider module, MCP registrar, and CLI command stubs for `ph.1-core`.

---

## Context & Goals

**Phase goal**: Create the structural skeleton for the OMP (Oh My Pi) wrap integration — the provider module (`headroom/providers/omp/`), the per-agent MCP registrar (`headroom/mcp_registry/omp.py`), and the `wrap omp` / `unwrap omp` CLI command stubs. This change delivers the modules only; runtime wiring (proxy startup, models.yml mutation, MCP registration calls, OMP launch) is deferred to `ph.2-integration`.

**Why this change exists**: `headroom wrap omp` (FR-1) and `headroom unwrap omp` (FR-2) need three pieces of code before they can be wired up: (a) YAML/JSON config helpers that know where OMP's files live and how to back them up, (b) an MCP registrar that speaks OMP's `mcpServers` schema, and (c) Click command registrations so `headroom wrap --help` advertises the subcommand and the unwrap sibling exists. This change builds all three in isolation, against ph.2's exact interface contracts, so ph.2 can drop straight into the call sites without re-shaping the module surface.

**Core design goals** (≤3):
1. **Mirror `headroom/providers/opencode/` exactly** — same file split (`__init__.py` + `config.py` + `runtime.py`), same naming conventions (`*_config_paths`, `snapshot_*_if_unwrapped`, `*_headroom_blocks`), same Click decorator shapes. A maintainer who knows the OpenCode module should be able to navigate the OMP module without learning a new layout.
2. **Adapt only where OMP genuinely differs** — YAML instead of JSON for `models.yml`, `mcpServers` (VSCode/Cursor style) instead of `mcp` for `.omp/mcp.json`, marker comments `# --- Headroom ... ---` instead of `// --- Headroom ... ---`. No other behavioral divergence from the opencode pattern.
3. **Phase-1 is scaffolding only** — every function is implemented and importable, but the CLI commands raise `NotImplementedError`. No models.yml mutation, no MCP registration invocation, no OMP binary launch. ph.2 owns the runtime calls.

---

## Technical Approach

### Architecture Diagram

```text
                  ┌─────────────────────────────────────────────────────┐
                  │   headroom/cli/wrap.py [MODIFIED]                   │
                  │   ┌──────────────────────────────────────────────┐   │
                  │   │ @wrap.command("omp") → def omp(...)          │   │
                  │   │   └─ raises NotImplementedError (STUB)       │   │
                  │   │ @unwrap.command("omp") → def unwrap_omp(...) │   │
                  │   │   └─ raises NotImplementedError (STUB)       │   │
                  │   └──────────────────────────────────────────────┘   │
                  └────────┬─────────────────────────────┬──────────────┘
                           │ (ph.2 will import from)    │
                           ▼                             ▼
       ┌───────────────────────────────┐   ┌────────────────────────────┐
       │ headroom/providers/omp/       │   │ headroom/mcp_registry/     │
       │            [NEW]              │   │   omp.py [NEW]             │
       │ ┌─────────────────────────┐   │   │                            │
       │ │ __init__.py             │   │   │  class OmpRegistrar        │
       │ │   exports: see below    │   │   │    extends MCPRegistrar    │
       │ ├─────────────────────────┤   │   │    name="omp"              │
       │ │ config.py               │◄──┼───│    detect/get_server/      │
       │ │   path helpers          │   │   │    register/unregister     │
       │ │   snapshot/inject/strip │   │   │    (mcpServers key format) │
       │ │   restore               │   │   │                            │
       │ ├─────────────────────────┤   │   └────────────────────────────┘
       │ │ runtime.py              │   │
       │ │   proxy_base_url()      │   │
       │ │   build_launch_env()    │   │
       │ └─────────────────────────┘   │
       └───────────────┬───────────────┘
                       │ (pattern reference)
                       ▼
       ┌───────────────────────────────┐
       │ headroom/providers/opencode/  │
       │       [EXISTING - REFERENCE]   │
       │   __init__.py / config.py /    │
       │   runtime.py / install.py      │
       └───────────────────────────────┘
```

### Core Data Structures

This change introduces no new dataclasses or enums; it reuses the existing `MCPRegistrar`, `ServerSpec`, `RegisterResult`, `RegisterStatus` from `headroom/mcp_registry/base.py`. The only "data" shapes are file-format-specific dicts parsed at runtime.

**File-format dicts** (parsed at runtime, not exported types):

```python
# ~/.omp/agent/models.yml — YAML format
models_yml_data: dict[str, Any]  # top-level keys; "providers" expected
#   providers: dict[str, dict[str, Any]]
#     <name>:
#       baseUrl: str              # the field we rewrite
#       ...                       # all other fields preserved verbatim

# .omp/mcp.json — JSON format (project-local)
mcp_json_data: dict[str, Any]    # top-level keys; "mcpServers" expected
#   $schema: str                 # optional
#   disabledServers: list        # optional
#   mcpServers: dict[str, dict[str, Any]]
#     headroom:
#       command: str             # "headroom"
#       args: list[str]          # ["mcp", "serve"]
#       env: dict[str, str]      # optional

# .omp/config.yml — YAML format (project-local)
config_yml_data: dict[str, Any]  # we only inject a marked headroom: block
#   headroom:
#     proxy_port: int
#     version: "1.0"
```

**Marker constants** (module-private, exported via `__init__.py` for unwrap reuse):

```python
_CONFIG_MARKER_START = "# --- Headroom proxy config ---"
_CONFIG_MARKER_END   = "# --- end Headroom proxy config ---"
```

(Only the `config.yml` marker is needed for ph.1 strip/restore. `models.yml` uses the byte-for-byte backup file for restoration — no marker is required there.)

### Data Flow

This change contains **no runtime invocation flow** — ph.1 only writes modules. The flow described here is what ph.2 will execute against the new module surface; documenting it so the module surface aligns with the intended caller.

```
[ph.2: headroom wrap omp invoked by user]
  └─► [ph.2 calls snapshot_omp_models_if_unwrapped(config, backup)]
        └─► read models.yml → if no backup yet & no markers → shutil.copy2(config, backup)
  └─► [ph.2 calls inject_omp_proxy_config(port)]
        ├─► re-snapshot if needed
        ├─► parse models.yml (yaml.safe_load)
        ├─► for each providers[k]: if "baseUrl" → rewrite to proxy_base_url(port)
        ├─► write models.yml back (yaml.dump, indent=2, sort_keys=False)
        ├─► create .omp/ dir, OmpRegistrar writes .omp/mcp.json (mcpServers.headroom)
        └─► append marker-wrapped headroom: block to .omp/config.yml
  └─► [ph.2 calls build_launch_env(port) → HEADROOM_PROXY_URL]
  └─► [ph.2 spawns `omp` subprocess]

[ph.2: headroom unwrap omp]
  └─► [ph.2 calls restore_omp_models_yml()]
        ├─► if backup exists → shutil.copy2(backup, config); unlink backup
        └─► else if models.yml exists & has markers → strip markers, write back
  └─► [OmpRegistrar.unregister_server("headroom")]
  └─► [ph.2 strips marker block from .omp/config.yml via strip_omp_headroom_blocks]
```

### Interface Design

All signatures follow the `headroom/providers/opencode/` public surface exactly, with OMP-specific paths and YAML/JSON adaptations.

#### `headroom/providers/omp/config.py`

```python
def omp_home_dir() -> Path:
    """Return the OMP user config directory (~/.omp/agent/).
    Honors PI_CODING_AGENT_DIR env var, mirroring _opencode_home_dir()'s OPENCODE_HOME pattern."""

def omp_models_yml_path() -> Path:
    """Return ~/.omp/agent/models.yml path (YAML provider config)."""

def omp_mcp_config_path() -> Path:
    """Return the project-local .omp/mcp.json path (Path.cwd() / '.omp' / 'mcp.json')."""

def omp_config_paths() -> tuple[Path, Path]:
    """Return (config_file, backup_file) for models.yml.
    backup_file = config_file.with_suffix('.yml.headroom-backup')."""

def snapshot_omp_models_if_unwrapped(config_file: Path, backup_file: Path) -> None:
    """Snapshot models.yml to backup_file before the first injection.
    Idempotent: skip if backup exists, if source absent, or if markers already present."""

def strip_omp_headroom_blocks(content: str) -> str:
    """Remove all Headroom-managed blocks from config.yml YAML text.
    Preserves user content. Uses _CONFIG_BLOCK_RE; collapses excess blank lines."""

def inject_omp_proxy_config(port: int) -> None:
    """Modify models.yml provider baseUrls to proxy; write .omp/mcp.json; mark .omp/config.yml.
    Full implementation in ph.1 scope — but no CLI caller invokes it yet (ph.2 wiring)."""

def restore_omp_models_yml() -> tuple[str, Path]:
    """Restore models.yml from backup or strip markers.
    Returns (status, path) where status in {'restored','cleaned','noop','removed'}."""
```

#### `headroom/providers/omp/runtime.py`

```python
def proxy_base_url(port: int) -> str:
    """Return the local proxy base URL used by OMP integrations.
    Format: http://127.0.0.1:{port}/v1 — identical to opencode's proxy_base_url."""

def build_launch_env(
    port: int,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Build environment variables for launching OMP through Headroom.
    Sets HEADROOM_PROXY_URL=http://127.0.0.1:{port} for the headroom MCP server.
    Returns (env, display_lines).
    Unlike opencode, OMP needs no OPENCODE_CONFIG_CONTENT — config is file-based."""
```

#### `headroom/mcp_registry/omp.py`

```python
class OmpRegistrar(MCPRegistrar):
    """Register MCP servers with OMP via project-local .omp/mcp.json (mcpServers key)."""

    name: str = "omp"
    display_name: str = "OMP"

    def __init__(self, *, config_path: Path | None = None) -> None:
        """config_path defaults to Path.cwd() / '.omp' / 'mcp.json'."""

    def detect(self) -> bool:
        """True iff `omp` is in PATH or a .omp/ directory exists at cwd."""

    def get_server(self, server_name: str) -> ServerSpec | None:
        """Return the registered ServerSpec from data['mcpServers'][name], or None."""

    def register_server(self, spec: ServerSpec, *, force: bool = False) -> RegisterResult:
        """Idempotent registration; ALREADY/MISMATCH/REGISTERED/FAILED semantics
        match OpencodeRegistrar. Serializes spec to {command, args, env} under mcpServers."""

    def unregister_server(self, server_name: str) -> bool:
        """Remove data['mcpServers'][server_name]; pop empty mcpServers; save."""

    # Module-private helpers (mirror OpencodeRegistrar):
    # _read_json, _write_json, _entry_to_spec, _spec_to_entry,
    # _specs_equivalent, _diff_specs
```

#### `headroom/cli/wrap.py` additions (stubs)

```python
@wrap.command(context_settings={"ignore_unknown_options": True})
@click.option("--port", "-p", default=8787, type=click.IntRange(1, 65535), help="Proxy port (default: 8787)")
@click.option("--no-mcp", is_flag=True, help="Skip headroom MCP server registration")
@click.option("--no-proxy", is_flag=True, help="Skip proxy startup (use existing proxy)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--prepare-only", is_flag=True, hidden=True)
@click.argument("omp_args", nargs=-1, type=click.UNPROCESSED)
def omp(port: int, no_mcp: bool, no_proxy: bool, verbose: bool,
        prepare_only: bool, omp_args: tuple) -> None:
    """Launch OMP through Headroom proxy. [NOT YET IMPLEMENTED]"""
    raise NotImplementedError(
        "`headroom wrap omp` is not yet implemented. "
        "Use `headroom wrap` with other agents (opencode, claude, codex) in the meantime. "
        "See ph.2 for the full wrap implementation."
    )

@unwrap.command("omp")
@click.option("--port", "-p", default=8787, type=click.IntRange(1, 65535), help="Proxy port (default: 8787)")
@click.option("--no-stop-proxy", is_flag=True, help="Do not stop the local Headroom proxy")
def unwrap_omp(port: int, no_stop_proxy: bool) -> None:
    """Undo ``headroom wrap omp`` edits. [NOT YET IMPLEMENTED]"""
    raise NotImplementedError(
        "`headroom unwrap omp` is not yet implemented. "
        "See ph.2 for the full unwrap implementation."
    )
```

Note: The option set on `wrap omp` is **deliberately smaller** than `wrap opencode` — no `--no-rtk` (OMP doesn't use a CLI context tool per KD-5), no `--no-serena`, no `--code-graph`, no `--learn`/`--memory`, no `--backend`/`--anyllm-provider`/`--region`. These can be added in ph.2 if the integration requires them.

---

## File Manifest

| File Path | Description | Action |
|-----------|-------------|--------|
| `headroom/providers/omp/__init__.py` | Package init; re-exports `omp_config_paths`, `omp_home_dir`, `omp_models_yml_path`, `omp_mcp_config_path`, `snapshot_omp_models_if_unwrapped`, `strip_omp_headroom_blocks`, `inject_omp_proxy_config`, `restore_omp_models_yml`, `_CONFIG_MARKER_START`, `_CONFIG_MARKER_END`, `proxy_base_url`, `build_launch_env`. Mirrors `headroom/providers/opencode/__init__.py` shape. | Create |
| `headroom/providers/omp/config.py` | All OMP config helpers (paths, snapshot, inject, strip, restore). Uses PyYAML (`yaml.safe_load`/`yaml.dump`) for `models.yml` + `config.yml`; stdlib `shutil` for backup. Module-private `_CONFIG_BLOCK_RE` regex + marker constants. | Create |
| `headroom/providers/omp/runtime.py` | `proxy_base_url` + `build_launch_env`. Minimal env: sets `HEADROOM_PROXY_URL=http://127.0.0.1:{port}`. No `OPENCODE_CONFIG_CONTENT`-equivalent — OMP is file-configured. | Create |
| `headroom/mcp_registry/omp.py` | `OmpRegistrar` class extending `MCPRegistrar`. Reads/writes `.omp/mcp.json` `mcpServers` key (VSCode/Cursor format). Mirror `OpencodeRegistrar` shape: same private helpers (`_read_json`, `_write_json`, `_entry_to_spec`, `_spec_to_entry`, `_specs_equivalent`, `_diff_specs`), same `RegisterStatus` semantics. | Create |
| `headroom/cli/wrap.py` | Add `@wrap.command("omp")` stub + `@unwrap.command("omp")` stub. Both raise `NotImplementedError` with a ph.2 pointer. Append after the existing `@wrap.command(...)` block that registers `wrap opencode` (≈ line 5447) and after `@unwrap.command("opencode")` (≈ line 5615). | Modify |

---

## Test Strategy

### Unit Tests

Per phase plan: **no tests written in ph.1**. The deliverable is a structural skeleton — ph.3 (`ph.3-hardening`) is the explicit owner of `test_providers_omp_config.py` and `test_mcp_registry_omp.py` per `bp/roadmap.md`. ph.2 needs the importable surface to exist before it can write meaningful behavioral tests against the runtime calls.

What ph.1 must guarantee for ph.2's tests to land cleanly:
- Every public function in `config.py` and `runtime.py` is importable from `headroom.providers.omp` (via `__init__.py` re-exports).
- `OmpRegistrar` is importable from `headroom.mcp_registry` (ph.2 will register it in the registrar fleet, parallel to `OpencodeRegistrar`).
- `headroom wrap omp --help` exits 0 and lists the documented options.
- `headroom wrap omp` exits non-zero with `NotImplementedError` mentioning ph.2.
- `headroom unwrap omp --help` exits 0.
- `headroom unwrap omp` exits non-zero with `NotImplementedError`.

### Integration Tests

Deferred to ph.3 (`test_wrap_omp.py`).

### TDD Tasks

**No TDD tasks.** All five tasks in this change are `type:scaffolding` — they create files or add command registrations without observable runtime behavior beyond importability and `--help` shape. The first genuinely behavioral implementation lands in ph.2, which owns the RED→GREEN→REFACTOR protocol.

---

## Alternatives

| Approach | Pros | Cons | Rejection Reason |
|----------|------|------|------------------|
| Single monolithic `omp.py` file in `headroom/providers/` | Fewer files to create | Violates D1 (opencode pattern); harder for maintainers who already know the opencode split; can't reuse `__init__.py` export pattern | **Rejected** — consistency with the rest of the codebase |
| `config/` subpackage with separate YAML/JSON helpers | Clean separation between models.yml and mcp.json concerns | Over-engineered for 3-4 functions; no other provider does this | **Rejected** — overkill at this size |
| Inject a new `headroom` provider entry into models.yml (instead of in-place baseUrl rewrite) | Less invasive; cleaner diff; matches opencode's provider-injection approach | OMP resolves models by provider id; we'd need every existing `provider/model` reference to switch to `headroom/...`, which the proxy layer doesn't currently support. C2 in stack research flags this. | **Rejected** — breaks user model references; C2 specifies in-place rewrite |
| Skip the MCP registrar in ph.1, defer to ph.2 | One fewer file this change | Then ph.2 must add a registrar AND its caller; ph.2 is already full | **Rejected** — registrar surface is small and stable; pull it forward |
| CLI stubs that print "coming in ph.2" instead of raising | Slightly less alarming for users | Silent no-op is worse than a clear error — accidentally running `headroom wrap omp` would silently do nothing | **Rejected** — D5 mandates `NotImplementedError` |
| Use the opencode module's helpers directly with a `provider: "omp"` switch | No new module | Couples omp/opencode; OMP's YAML schema is materially different from opencode.json; tests would need to mock differently | **Rejected** — divergence in file formats requires divergent code |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| `yaml.dump` round-trip loses user comments / key ordering, making unwrap non-byte-identical | High | Medium — user sees changes to their models.yml they didn't author | Backup-first approach (`models.yml.headroom-backup`) guarantees byte-for-byte restoration on unwrap. The inject function is idempotent and rewrites the file in full — comments lost are comments that would be lost on any future save by OMP itself. Document in `runtime.py` module docstring that models.yml restoration comes from the backup, not from marker stripping. |
| `OmpRegistrar.detect()` returns false positives (`.omp/` exists but no `omp` binary) | Low | Low — ph.2 will only call `.register_server()` after `wrap omp` is invoked, not from auto-install | `detect()` is a hint, not a gate. ph.2's `wrap omp` always proceeds because the user explicitly requested OMP. Fleet-wide auto-install (in `headroom/mcp_registry/install.py`) would skip omp when `shutil.which("omp")` is None, matching opencode's existing heuristic. |
| `headroom wrap omp --help` conflicts with another Click command name | Very Low | High — registration would crash at import time | `omp` is unused elsewhere in `headroom/cli/wrap.py` (verified by reading `wrap.py`). Adding it at the end of the wrap block preserves load order. |
| `OmpRegistrar` writes corrupt JSON if existing `.omp/mcp.json` has trailing junk or BOM | Low | Medium — breaks OMP MCP discovery | `_read_json` returns `{}` on parse error (mirrors `OpencodeRegistrar._read_json`), so a corrupt file gets replaced cleanly. User loses other OMP MCP entries — ph.3 should add a backup-before-overwrite safety net. |
| CLI stubs accidentally called by ph.1's verification | Low | Low — produces a clear NotImplementedError | Verification check (`headroom wrap omp` should exit non-zero with NotImplementedError) is the test that the stubs are in place. |
| pyyaml version skew (`yaml.safe_load`/`yaml.dump` semantics) | Very Low | Low — PyYAML 6.0.3 is pinned in project deps (per `bp/milestones/M1-omp-wrap/phases/ph.1-core/research.md` §1c) | No mitigation needed beyond the existing pin. |