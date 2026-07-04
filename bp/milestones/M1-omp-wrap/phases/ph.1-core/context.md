# Context: ph.1-core

> Phase implementation decisions for OMP provider module, MCP registrar, and CLI stubs.

---

## Phase Goals

Create the OMP provider module (`headroom/providers/omp/`), MCP registrar (`headroom/mcp_registry/omp.py`), and CLI command skeleton matching the Opencode provider pattern.

---

## Architecture Decisions

### D1: Module structure follows opencode pattern
- **Decision**: `headroom/providers/omp/config.py` (snapshot/inject/strip helpers), `headroom/providers/omp/runtime.py` (launch env builder), `headroom/providers/omp/__init__.py` (exports)
- **Rationale**: Consistency with existing `headroom/providers/opencode/` — minimises learning curve for maintainers
- **Alternatives considered**: Single monolithic file; separate directory per file type

### D2: Backup suffix matches opencode
- **Decision**: `.headroom-backup` backup suffix for models.yml and other modified files
- **Rationale**: Matches opencode convention; unwrap code can share patterns
- **Alternatives considered**: `.omp-backup`, `.headroom-omp-backup`

### D3: YAML comment markers for config.yml
- **Decision**: `# --- Headroom proxy provider ---` / `# --- end Headroom ---` for `.omp/config.yml`
- **Rationale**: Matches opencode's `// --- Headroom ... ---` JSON comment convention, adapted for YAML
- **Alternatives considered**: Separate backup file only

### D4: OmpRegistrar writes to .omp/mcp.json
- **Decision**: `OmpRegistrar` extends `MCPRegistrar` ABC and writes to `.omp/mcp.json` (project-local)
- **Rationale**: Follows `OpencodeRegistrar` pattern; project-level scope per user preference
- **Alternatives considered**: User-level `~/.omp/agent/mcp.json`

### D5: CLI stubs are compile-time placeholder
- **Decision**: `wrap omp` and `unwrap omp` CLI commands registered but raise `NotImplementedError` with a clear message pointing to ph.2
- **Rationale**: Allows early integration into wrap command structure; prevents accidental usage
- **Alternatives considered**: No-op graceful message; fully functional but limited

---

## Interface Contracts

### `headroom/providers/omp/config.py`

```python
def omp_models_yml_path() -> Path:
    """Return ~/.omp/agent/models.yml path."""

def omp_config_paths() -> tuple[Path, Path]:
    """Return (config_file, backup_file) for models.yml."""

def snapshot_omp_models_if_unwrapped(config_file: Path, backup_file: Path) -> None:
    """Backup models.yml before first injection (idempotent)."""

def inject_omp_proxy_config(port: int) -> None:
    """Modify models.yml provider baseUrl's to proxy; write .omp/mcp.json; mark .omp/config.yml."""

def strip_omp_headroom_blocks(content: str) -> str:
    """Remove Headroom-managed blocks from config strings."""

def restore_omp_models_yml() -> tuple[str, Path]:
    """Restore models.yml from backup or strip markers."""

def omp_home_dir() -> Path:
    """Return the OMP user config directory (~/.omp/agent/)."""

def omp_mcp_config_path() -> Path:
    """Return .omp/mcp.json path."""
```

### `headroom/mcp_registry/omp.py`

```python
class OmpRegistrar(MCPRegistrar):
    """Register/unregister MCP servers with OMP (.omp/mcp.json)."""
```

### `headroom/cli/wrap.py` additions

```python
@wrap.command("omp", ...)
def omp(port, no_rtk, no_mcp, no_serena, code_graph, no_proxy, learn, memory, verbose, prepare_only, omp_args):
    """Launch OMP through Headroom proxy. [STUB — NotImplementedError]"""

@unwrap.command("omp")
def unwrap_omp(port, no_stop_proxy):
    """Undo ``headroom wrap omp`` edits. [STUB — NotImplementedError]"""
```

---

## Implementation Constraints

- All new files follow `headroom/providers/opencode/` structure exactly
- PyYAML 6.0.3 is already installed (no new deps)
- `headroom/providers/omp/config.py` must not import from ph.2-only modules
- `OmpRegistrar.detect()` checks `.omp/` directory exists
- Models.yml modification: modify `baseUrl` in each provider entry; preserve all other fields

---

## Change Split Plan

1. Create `headroom/providers/omp/__init__.py` — exports
2. Create `headroom/providers/omp/config.py` — all config helpers (snapshot, inject, strip, restore)
3. Create `headroom/providers/omp/runtime.py` — proxy_base_url, build_launch_env
4. Create `headroom/mcp_registry/omp.py` — OmpRegistrar class
5. Add `wrap omp` + `unwrap omp` CLI commands to `headroom/cli/wrap.py` (stubs)
6. Verify: `headroom wrap omp --help` works; `headroom wrap omp` prints NotImplementedError

---

## Non-Goals

- Full wrap/unwrap workflow (ph.2)
- Integration tests (ph.3)
- models.yml actual modification at runtime (ph.2)
- `.omp/mcp.json` actual MCP registration at runtime (ph.2)
