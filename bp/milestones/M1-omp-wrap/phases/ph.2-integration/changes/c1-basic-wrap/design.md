# Design: c1-basic-wrap

> Fill `headroom wrap omp` and `headroom unwrap omp` NotImplementedError stubs with real CLI wiring: proxy startup, MCP registration via `OmpRegistrar`, OMP launch via `_launch_tool`, and unwrap that restores models.yml, removes MCP registration, and stops the proxy.

---

## Context & Goals

c1-basic-wrap implements the CLI wiring layer for OMP wrap/unwrap. Two stubs in `headroom/cli/wrap.py` currently raise `NotImplementedError`; this change replaces them with real implementations that follow the established `opencode()` / `unwrap_opencode()` patterns.

The change stays narrowly within CLI wiring — it does **not** add new config-injection logic, upstream-mapping logic, or proxy pipeline extensions. Those are owned by sibling changes (c2-models-yml-inject, c3-proxy-extensions) per the phase split plan in `context.md`.

**Goals** (≤3):
1. Wire `wrap omp` to start the proxy, register the headroom MCP server, and launch the `omp` binary.
2. Wire `unwrap omp` to restore `models.yml` from backup, remove the headroom MCP entry, and stop the local proxy.
3. Match the `opencode()` click-command surface so downstream tooling and tests treat the two agents uniformly.

**Non-goals** (explicit from proposal):
- `models.yml` baseUrl modification (c2)
- `.omp/.headroom-upstreams.json` upstream mapping file (c2)
- `HEADROOM_OMP_UPSTREAM_MAP` env var propagation (c3)
- Proxy pipeline extensions (`x-headroom-base-url`, `OmpUpstreamRouterTransform`) (c3)
- Tests (ph.3-hardening)

---

## Technical Approach

### Architecture Diagram

```text
                       headroom wrap omp
                             │
                             ▼
        ┌────────────────────────────────────┐
        │  shutil.which("omp")  [EXISTING]   │
        └─────────────┬──────────────────────┘
                      │ not found → ClickException
                      │ "Install OMP: https://ohmy.pi"
                      ▼
        ┌────────────────────────────────────┐
        │  OmpRegistrar.register_server()    │   [EXISTING - ph.1]
        │  (skipped if --no-mcp)             │
        └─────────────┬──────────────────────┘
                      │ writes/updates
                      ▼
        ┌────────────────────────────────────┐
        │  .omp/mcp.json  [ON DISK]          │
        │  { mcpServers: { headroom: {...}}} │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  build_launch_env(port)            │   [EXISTING - ph.1]
        │  → HEADROOM_PROXY_URL set          │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  _launch_tool(                     │   [EXISTING]
        │    binary="omp",                   │
        │    env=env,                        │
        │    tool_label="OMP",               │
        │    agent_type="omp"                │
        │  )                                 │
        └─────────────┬──────────────────────┘
                      │ internally calls
                      ▼
        ┌────────────────────────────────────┐
        │  _ensure_proxy(port, no_proxy)     │   [EXISTING]
        │  → subprocess.Popen (uvicorn)      │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  subprocess.run(["omp", *args])    │   [EXISTING]
        │  → routes via http://127.0.0.1:... │
        └────────────────────────────────────┘

                       headroom unwrap omp
                             │
                             ▼
        ┌────────────────────────────────────┐
        │  restore_omp_models_yml()          │   [EXISTING - ph.1]
        │  - restore from backup, OR         │
        │  - strip markers, OR               │
        │  - remove if Headroom-only         │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  strip_omp_headroom_blocks(.omp/   │   [EXISTING - ph.1]
        │    config.yml)                     │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  OmpRegistrar.unregister_server(   │   [EXISTING - ph.1]
        │    "headroom")                     │
        └─────────────┬──────────────────────┘
                      │ edits
                      ▼
        ┌────────────────────────────────────┐
        │  .omp/mcp.json  [ON DISK]          │
        │  mcpServers.headroom removed       │
        └─────────────┬──────────────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  _stop_local_proxy_for_unwrap(     │   [EXISTING]
        │    port)  unless --no-stop-proxy   │
        └────────────────────────────────────┘
```

**Module touch map**:
- `headroom/cli/wrap.py` — **[MODIFIED]** `omp()` and `unwrap_omp()` function bodies (decorator block already present)
- All other modules — **[EXISTING]** consumed unchanged from ph.1 and earlier

### Core Data Structures

No new types are introduced in c1. The interface is composed entirely of existing ph.1 outputs:

- `OmpRegistrar` (`headroom/mcp_registry/omp.py`) — `register_server(spec, force=…)`, `unregister_server(name)`, `detect()`
- `ServerSpec` (`headroom/mcp_registry/base.py`) — already-typed MCP server description
- `build_launch_env(port, environ)` (`headroom/providers/omp/runtime.py`) — returns `(dict[str, str], list[str])`
- `restore_omp_models_yml()` (`headroom/providers/omp/config.py`) — returns `(status: str, path: Path)`
- `strip_omp_headroom_blocks(content: str)` (`headroom/providers/omp/config.py`) — pure helper
- `OmpRegistrar` does not need new fields; `force=True` is passed during register to handle pre-existing differing entries (matches `opencode()`)

### Data Flow

**Wrap — happy path**

1. Click dispatches `omp(...)` with options `{port, no_mcp, no_proxy, verbose, prepare_only, omp_args}`.
2. `shutil.which("omp")` resolves the binary. If `None` → raise `click.ClickException("OMP CLI 'omp' not found in PATH. Install OMP: https://ohmy.pi")` (matches `opencode()` SystemExit(1) style but uses ClickException for uniform error reporting).
3. If not `no_mcp` and `OmpRegistrar.detect()` (i.e. `.omp/` directory exists):
   - Build `ServerSpec` via existing `build_headroom_spec(f"http://127.0.0.1:{port}")`.
   - `OmpRegistrar.register_server(spec, force=True)` writes/updates `.omp/mcp.json`.
   - Print one-line status via `format_result(...)`.
4. `(env, env_vars_display) = build_launch_env(port, os.environ)` — sets `HEADROOM_PROXY_URL`.
5. If `prepare_only`: print a "preparation complete" line and return (do **not** call `_launch_tool`).
6. `_launch_tool(binary="omp", args=omp_args, env=env, port=port, no_proxy=no_proxy, tool_label="OMP", env_vars_display=env_vars_display, agent_type="omp")` — owns proxy startup, child launch, and cleanup.

**Unwrap — happy path**

1. Click dispatches `unwrap_omp(port, no_stop_proxy)`.
2. Print `HEADROOM UNWRAP: OMP` banner (mirror of `unwrap_opencode` banner).
3. `status, models_path = restore_omp_models_yml()` — restores from backup or strips markers.
4. If `.omp/config.yml` exists, read it, run `strip_omp_headroom_blocks(...)`, write back (remove file if result is empty).
5. `OmpRegistrar.unregister_server("headroom")` removes the headroom entry from `.omp/mcp.json`.
6. If `status != "noop"` and not `no_stop_proxy`: `_stop_local_proxy_for_unwrap(port)` and `_echo_unwrap_proxy_stop_status(...)`.
7. Print completion line.

**Unwrap — idempotent path**

- If `models.yml` has no backup and no markers → `restore_omp_models_yml()` returns `("noop", path)`.
- If `.omp/config.yml` doesn't exist → step 4 is a no-op.
- If `.omp/mcp.json` doesn't have `headroom` → `unregister_server` returns `True` (already-absent treated as success).
- Final stop-proxy branch is gated on `status != "noop"`, so a second unwrap on a clean tree is a pure no-op.

### Interface Design

**Modified function signatures** (the function bodies only — click decorator stack is unchanged):

```python
def omp(
    port: int,
    no_mcp: bool,
    no_proxy: bool,
    verbose: bool,
    prepare_only: bool,
    omp_args: tuple,
) -> None:
    """Launch OMP (Oh My Pi) through Headroom proxy.

    Starts the Headroom proxy, registers the headroom MCP server in
    ``.omp/mcp.json``, and launches the ``omp`` CLI with
    ``HEADROOM_PROXY_URL`` pointing at the local proxy.

    Behaviour summary:
      * Refuses to run if ``omp`` is not on PATH.
      * With ``--no-mcp``, skips MCP registration but still launches ``omp``.
      * With ``--prepare-only``, performs MCP registration (unless ``--no-mcp``)
        and returns without launching the binary.
    """

def unwrap_omp(port: int, no_stop_proxy: bool) -> None:
    """Undo ``headroom wrap omp`` edits to OMP configuration files.

    Behaviour:
      * Restores ``models.yml`` from ``models.yml.headroom-backup`` if present,
        otherwise strips Headroom markers from the active file.
      * Strips Headroom markers from ``.omp/config.yml`` if present.
      * Removes the headroom MCP entry from ``.omp/mcp.json``.
      * Stops the local Headroom proxy unless ``--no-stop-proxy``.
      * Safe no-op when nothing was wrapped.
    """
```

**No new helper functions** — all behaviour is composed from existing helpers. Two minor inline additions to `wrap.py`:

- A short OMP install URL constant (e.g. `_OMP_INSTALL_HINT`) near the existing context-tool constants for clarity in the binary-missing error path.
- A small block-strip helper `_strip_omp_config_markers(path: Path) -> str` returning `"stripped" | "removed" | "noop"` to mirror `restore_omp_models_yml`'s contract for the project config file. This is a private file-scope helper (~15 lines) — kept in `wrap.py` to avoid expanding `headroom/providers/omp/config.py` in c1.

---

## File Manifest

| File Path | Description | Action |
|-----------|-------------|--------|
| `headroom/cli/wrap.py` | Replace `omp()` body (lines 5626–5657); replace `unwrap_omp()` body (lines 5761–5778); add small `_strip_omp_config_markers` helper | Modify |
| `tests/test_cli/test_wrap_omp.py` | New test file covering wrap happy path, missing binary, `--no-mcp`, `--prepare-only`, unwrap restore, unwrap noop (mirrors `test_wrap_opencode.py`) | Create — **deferred to ph.3-hardening per proposal Non-goals** |

No other files are touched in c1. The ph.1 surface (`OmpRegistrar`, `inject_omp_proxy_config`, `restore_omp_models_yml`, `build_launch_env`, `_launch_tool`, `_ensure_proxy`, `_setup_headroom_mcp`, `_stop_local_proxy_for_unwrap`) is reused as-is.

---

## Test Strategy

> **Per proposal Non-goals: tests are out of scope for c1 (ph.3-hardening owns them).** The strategy below is the **executable acceptance contract** — ph.3 will materialize it as `pytest` cases. Type:behavior tasks below MUST therefore include the RED-test description in GIVEN/WHEN/THEN so reviewers can trace the spec to a future test.

### Unit Tests (planned for ph.3, contract captured here)

| Scenario | Mock surface | Assertion |
|----------|--------------|-----------|
| `wrap omp` happy path | `shutil.which→"omp"`, `_launch_tool→fake`, `OmpRegistrar.register_server→REGISTERED` | `_launch_tool` called with `binary="omp"`, `agent_type="omp"`, env contains `HEADROOM_PROXY_URL`; MCP register invoked |
| `wrap omp` missing binary | `shutil.which→None` | `ClickException` raised; `_launch_tool` not called |
| `wrap omp --no-mcp` | `shutil.which→"omp"`, `_launch_tool→fake` | `OmpRegistrar.register_server` not called; `_launch_tool` still called |
| `wrap omp --prepare-only` | `shutil.which→"omp"` | `_launch_tool` NOT called; process exits 0 |
| `unwrap omp` restore from backup | `.omp/agent/models.yml.headroom-backup` present | `models.yml` byte-identical to backup, backup removed, `OmpRegistrar.unregister_server` called |
| `unwrap omp` noop | No backup, no markers, no MCP entry | No filesystem writes; proxy not stopped; exit 0 |
| `unwrap omp --no-stop-proxy` | Pre-wrapped state | Proxy stop helper NOT invoked |

### Integration Tests (planned for ph.3)

A single end-to-end test that boots a fake `omp` binary (writes PID, sleeps) and verifies that:
- The proxy is listening on the configured port after `wrap omp` exits.
- The fake `omp` subprocess receives `HEADROOM_PROXY_URL` in its environment.
- `.omp/mcp.json` contains the headroom entry.
- `unwrap omp` cleans all of the above.

### TDD Tasks

Both Wave 1 and Wave 2 tasks are `type:behavior` and have RED-test descriptions embedded in `tasks.md`. Reviewers must confirm the GIVEN/WHEN/THEN trace matches `bp/specs/omp/spec.md`.

---

## Alternatives

| Approach | Pros | Cons | Rejection Reason |
|----------|------|------|------------------|
| **Inline OMP install instructions in `click.echo` + `SystemExit(1)`** (matches `opencode()`) | Uniform with sibling command | Loses structured ClickException behaviour; harder for callers to programmatically detect failure | **Not used** — use `click.ClickException` for typed error reporting consistent with the rest of `wrap.py` |
| **Call `inject_omp_proxy_config(port)` from `omp()`** (research.md suggested) | Models.yml + config.yml get rewritten by ph.1 function | Proposal explicitly excludes "models.yml modification (c2)"; would couple c1 to c2 | **Not used** — c2 will own the integration call; c1 wires CLI scaffolding only |
| **Custom local helper `_register_omp_mcp` instead of `_setup_headroom_mcp(OmpRegistrar(), …)`** | Slightly less code | Duplicates the existing generic MCP-setup path used by Claude/Codex/OpenCode | **Not used** — reuse `_setup_headroom_mcp(OmpRegistrar(), port, verbose=verbose, force=True)` for parity |
| **Skip MCP registration when `.omp/` does not exist** (i.e. fail-soft) | Avoids writing to a non-OMP project | `OmpRegistrar.detect()` already returns `False` in that case, and `_setup_headroom_mcp` short-circuits — no extra logic needed | **Already handled by `_setup_headroom_mcp`** — no extra branch needed |
| **Implement unwrap's config.yml stripping via inline regex instead of `strip_omp_headroom_blocks`** | Avoid importing `headroom/providers/omp/config.py` | Duplicates ph.1 helper | **Not used** — reuse the existing helper |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| `omp` binary on PATH but actually a different tool (e.g. `omp` is a generic name) | Low | Medium — wrong binary launched | Document OMP install location in error message; trust user to have correct `omp` (matches opencode assumption) |
| `OmpRegistrar.register_server` returns `MISMATCH` because user pre-existing `headroom` entry differs from ours | Medium | Low — proxy still launches, MCP tools missing | Pass `force=True` (matches `opencode()`); print overwrite hint via `format_result` |
| `unwrap_omp` deletes a backup the user wants to keep (e.g. for diff) | Low | Medium — data loss | The backup is `models.yml.headroom-backup`, a Headroom-managed file. Document the contract in docstring; restoration only deletes the backup on success |
| `unwrap_omp` run twice — second call sees no backup and no markers | High (expected) | None | Designed no-op; `status == "noop"` gates proxy stop so second call is silent |
| `strip_omp_headroom_blocks` on `.omp/config.yml` mangles user content if it coincidentally contains `# --- Headroom proxy config ---` | Very low | High — user data corruption | Markers are exactly the ph.1 marker strings; same risk as every other wrap command (opencode/codex/claude); accepted |
| `_launch_tool` swallows exceptions and the wrap appears to succeed | Low | Medium — proxy state leaks | `_launch_tool` already raises `SystemExit(1)` on failure; existing pattern is acceptable |
| User invokes `wrap omp` from outside an OMP project (no `.omp/`) | Medium | Low — `OmpRegistrar.detect()` returns False, MCP setup skipped silently | Document expected working directory; optionally print a verbose warning (matches `opencode()` verbose behaviour) |