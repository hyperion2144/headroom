# Tasks: c1-basic-wrap

> This document breaks the design into executable tasks grouped by wave. Each task includes description, files, acceptance criteria, optional depends_on and spec_ref. type:behavior tasks include RED test descriptions (GIVEN/WHEN/THEN format).
>
> **Test authoring is deferred to ph.3-hardening** (per `proposal.md` Non-goals). The RED-test descriptions below are the **executable acceptance contract** — ph.3 will materialize them as `pytest` cases in `tests/test_cli/test_wrap_omp.py`.

---

## TDD Type Annotations

| type | Meaning | TDD Protocol |
|------|---------|-------------|
| `behavior` | Business behavior — implement a concrete, observable/assertable feature | **RED→GREEN→REFACTOR** (mandatory: test first → implement → refactor) |
| `config` | Configuration — env vars, CI/CD, lint, tsconfig, etc. | Direct implementation, no TDD |
| `refactor` | Refactoring — improve internal structure without changing behavior | Verify tests pass → refactor → verify again |
| `docs` | Documentation — README, API docs, comments | Direct implementation, no TDD |
| `scaffolding` | Skeleton code — new module shells, directory structure, templates | Direct implementation, no TDD |

> **Rule**: If a task's core output is "a behavior" (user-perceptible or test-assertable), use `behavior`. If it's just "file exists" or "config takes effect", use `config`/`scaffolding`.

> **Spec reference for all c1 behavior tasks**: `bp/specs/omp/spec.md` already covers the OMP wrap/unwrap contract (it was bootstrapped from ph.1 scaffolding). c1 does not introduce new spec domains — it implements the scenarios that spec already describes. Future review should reconcile the scenarios here against `bp/specs/omp/spec.md` lines 49–71 (MCP registrar), lines 63–71 (launch), and lines 29–48 (unwrap restoration).

---

## Wave 1: Wire `headroom wrap omp`

- [x] task-1.1: [type:behavior] Implement `omp()` wrap command — binary check + MCP registration + launch <!-- commit: e6dc3622 -->
  - **description**: Replace the `raise NotImplementedError(...)` body of `omp()` in `headroom/cli/wrap.py` (lines 5626–5657) with the real implementation. Flow:
    1. `shutil.which("omp")` → if `None`, raise `click.ClickException("OMP CLI 'omp' not found in PATH. Install OMP: https://ohmy.pi")`. Use a new module-level constant `_OMP_INSTALL_URL = "https://ohmy.pi"` defined near other wrap constants (e.g. near line 163).
    2. Unless `no_mcp`: call `_setup_headroom_mcp(OmpRegistrar(), port, verbose=verbose, force=True)` to register the headroom MCP server in `.omp/mcp.json` (the registrar's `detect()` already short-circuits when `.omp/` is absent).
    3. `(env, env_vars_display) = build_launch_env(port, os.environ)`.
    4. If `prepare_only`: `click.echo("  OMP preparation complete (proxy not started, omp not launched).")` and `return`.
    5. Call `_launch_tool(binary="omp", args=omp_args, env=env, port=port, no_proxy=no_proxy, tool_label="OMP", env_vars_display=env_vars_display, agent_type="omp")`.
    6. Update the docstring to drop the "NOT YET FULLY IMPLEMENTED" notice and replace with the post-implementation behaviour summary (see `design.md` Interface Design).
    Imports needed at top of `omp()`: `from headroom.mcp_registry import OmpRegistrar`, `from headroom.providers.omp.runtime import build_launch_env`. `shutil` and `click` are already imported in `wrap.py`.
  - **files**: `headroom/cli/wrap.py`
  - **acceptance**:
    - `headroom wrap omp --help` shows the existing options unchanged.
    - `headroom wrap omp` from a directory with `.omp/` and `omp` on PATH: starts proxy, writes headroom MCP entry to `.omp/mcp.json`, launches `omp` subprocess with `HEADROOM_PROXY_URL` set.
    - `headroom wrap omp --no-mcp`: skips MCP registration but still launches `omp` via `_launch_tool`.
    - `headroom wrap omp --prepare-only`: registers MCP (unless `--no-mcp`), prints status, does NOT call `_launch_tool`, exits 0.
    - `headroom wrap omp` with `omp` not on PATH: exits non-zero with the install URL hint and does not start the proxy.
    - `NotImplementedError` no longer raised by `omp()`.
    - Lint clean (existing wrap.py lint passes).
  - **spec_ref**: `bp/specs/omp/spec.md`
  - ***RED test*** (wrap — happy path):
    ```
    GIVEN `omp` resolves via shutil.which and `.omp/mcp.json` is absent
    WHEN `headroom wrap omp --port 9000` is invoked with _launch_tool mocked
    THEN _launch_tool is called once with binary="omp", agent_type="omp", env containing HEADROOM_PROXY_URL=http://127.0.0.1:9000
    AND `.omp/mcp.json` contains mcpServers.headroom after the call
    ```
  - ***RED test*** (wrap — missing binary):
    ```
    GIVEN shutil.which("omp") returns None
    WHEN `headroom wrap omp` is invoked
    THEN the command raises click.ClickException with "Install OMP" in the message
    AND _launch_tool is never called
    AND the proxy is not started
    ```
  - ***RED test*** (wrap — --no-mcp):
    ```
    GIVEN `omp` resolves via shutil.which and `.omp/` exists
    WHEN `headroom wrap omp --no-mcp` is invoked with _launch_tool mocked
    THEN OmpRegistrar.register_server is never called
    AND _launch_tool is called once with binary="omp"
    ```
  - ***RED test*** (wrap — --prepare-only):
    ```
    GIVEN `omp` resolves via shutil.which
    WHEN `headroom wrap omp --prepare-only` is invoked
    THEN _launch_tool is never called
    AND the command exits 0
    ```

- [x] task-1.2: [type:scaffolding] Add `_OMP_INSTALL_URL` constant and import block for OMP wrap <!-- commit: 31cfabbe -->
  - **description**: Near the existing `_TOOL_SEARCH_ENV` / `_TOOL_SEARCH_DEFAULT` block in `headroom/cli/wrap.py` (around line 178), add `_OMP_INSTALL_URL = "https://ohmy.pi"` and a one-line comment explaining it backs the `omp`-not-found error. This is split from task-1.1 only because the lint clean-up (constants separated from implementation) makes the diff reviewer-friendly. If implementation discovers the constant must live elsewhere, the constant moves but task-1.1's binary check still references it by name.
  - **files**: `headroom/cli/wrap.py`
  - **acceptance**: Constant is module-level, type is `str`, value is `"https://ohmy.pi"`. No behavioural change on its own.
  - **depends_on**: [task-1.1] (constant is only consumed by task-1.1)

---

## Wave 2: Wire `headroom unwrap omp`

- [x] task-2.1: [type:behavior] Implement `unwrap_omp()` — restore models.yml + strip .omp/config.yml markers + unregister MCP + stop proxy <!-- commit: c3811e63 -->
  - **description**: Replace the `raise NotImplementedError(...)` body of `unwrap_omp()` in `headroom/cli/wrap.py` (lines 5761–5778) with the real implementation. Flow:
    1. Print `HEADROOM UNWRAP: OMP` banner (mirror `unwrap_opencode()` lines 5693–5697 verbatim, substituting `OMP` for `OPENCODE`).
    2. `status, models_path = restore_omp_models_yml()` — handles restore-from-backup / strip-markers / remove-file / noop. Map returned status to a human line: `restored→"Restored prior {path} from pre-wrap backup."`, `cleaned→"Stripped Headroom markers from {path}."`, `removed→"Removed {path} (contained only Headroom content)."`, `noop→"Nothing to undo: {path} has no Headroom wrap markers."` (mirror `unwrap_opencode()` lines 5699–5728).
    3. Strip `.omp/config.yml` markers via a new private helper `_strip_omp_config_markers(path: Path) -> str` placed directly above `unwrap_omp` (or just above it in the file). Helper reads the file, applies `strip_omp_headroom_blocks(...)` from `headroom.providers.omp.config`, writes back, removes the file if result is empty. Returns one of `"stripped" | "removed" | "noop"`. The unwrap function calls it on `Path.cwd() / ".omp" / "config.yml"` and echoes a one-line summary when status != `"noop"`.
    4. `OmpRegistrar = OmpRegistrar()` (imported via `from headroom.mcp_registry import OmpRegistrar`). If `OmpRegistrar.detect()`: `OmpRegistrar.unregister_server("headroom")` and echo `"  Removed Headroom MCP server from OMP."` on True. Match `unwrap_opencode()` lines 5732–5738 semantics exactly.
    5. Echo `✓ OMP is no longer routed through the Headroom proxy.`
    6. If `status != "noop"` and not `no_stop_proxy`: `_echo_unwrap_proxy_stop_status(_stop_local_proxy_for_unwrap(port), port)`.
    7. Update the docstring to drop the "NOT YET FULLY IMPLEMENTED" notice and describe post-implementation behaviour (see `design.md` Interface Design).
    Imports needed at top of `unwrap_omp`: `from headroom.mcp_registry import OmpRegistrar`, `from headroom.providers.omp.config import restore_omp_models_yml, strip_omp_headroom_blocks`.
  - **files**: `headroom/cli/wrap.py`
  - **acceptance**:
    - `headroom unwrap omp --help` shows the existing options unchanged.
    - `headroom unwrap omp` from a previously-wrapped state with a `.omp/agent/models.yml.headroom-backup` present: restores `models.yml` byte-for-byte, removes the backup, removes headroom from `.omp/mcp.json`, stops the local proxy on the configured port.
    - `headroom unwrap omp` from a wrapped state without a backup but with Headroom markers in `models.yml`: strips the markers, removes headroom MCP entry, stops the proxy.
    - `headroom unwrap omp` from a clean (never-wrapped) state: prints a "nothing to undo" line for each artifact, exits 0, does NOT stop the proxy (because `status == "noop"`).
    - `headroom unwrap omp --no-stop-proxy`: performs all restoration, prints a "proxy left running" hint, does NOT call `_stop_local_proxy_for_unwrap`.
    - The `.omp/config.yml` Headroom marker block (when present) is stripped on unwrap.
    - `NotImplementedError` no longer raised by `unwrap_omp()`.
    - Second consecutive `unwrap omp` is a safe no-op (idempotent).
    - Lint clean.
  - **depends_on**: [task-1.1]
  - **spec_ref**: `bp/specs/omp/spec.md`
  - ***RED test*** (unwrap — restore from backup):
    ```
    GIVEN a previous wrap created `~/.omp/agent/models.yml.headroom-backup`
    AND `.omp/mcp.json` contains mcpServers.headroom
    WHEN `headroom unwrap omp --port 8787` is invoked
    THEN `models.yml` is byte-identical to the backup
    AND the backup file is removed
    AND `.omp/mcp.json` no longer contains the headroom key
    AND _stop_local_proxy_for_unwrap(8787) is called
    ```
  - ***RED test*** (unwrap — strip markers when no backup):
    ```
    GIVEN no backup exists but `~/.omp/agent/models.yml` contains "# --- Headroom proxy config ---" markers
    WHEN `headroom unwrap omp` is invoked
    THEN the markers are stripped from models.yml
    AND non-Headroom content is preserved
    ```
  - ***RED test*** (unwrap — strip .omp/config.yml markers):
    ```
    GIVEN `<cwd>/.omp/config.yml` contains the Headroom marker block
    WHEN `headroom unwrap omp` is invoked
    THEN the marker block is removed
    AND any non-Headroom content is preserved
    ```
  - ***RED test*** (unwrap — noop when clean):
    ```
    GIVEN no backup exists, no Headroom markers in models.yml or .omp/config.yml, no headroom MCP entry
    WHEN `headroom unwrap omp` is invoked
    THEN no files are modified
    AND _stop_local_proxy_for_unwrap is NOT called
    AND the command exits 0
    ```
  - ***RED test*** (unwrap — --no-stop-proxy):
    ```
    GIVEN a previously-wrapped state with backup present
    WHEN `headroom unwrap omp --no-stop-proxy` is invoked
    THEN models.yml is restored and backup removed
    AND _stop_local_proxy_for_unwrap is NOT called
    ```

---

## Verification

- [x] `headroom wrap omp --help` and `headroom unwrap omp --help` render unchanged option surface
- [x] Manual smoke: `headroom wrap omp --prepare-only` in a temp dir with a fake `.omp/mcp.json` writes the headroom entry and exits 0
- [x] Manual smoke: `headroom unwrap omp` after a wrap is idempotent (second run = noop, no proxy stop)
- [x] Manual smoke: `shutil.which("omp")` overridden to `None` → `wrap omp` exits non-zero with "Install OMP" hint
- [x] No `NotImplementedError` in `omp()` or `unwrap_omp()` (search confirms)
- [x] Lint clean (existing wrap.py lint config passes)
- [x] Type check clean (`mypy`/`pyright` if configured)
- [x] All opencode wrap/unwrap tests still pass (`tests/test_cli/test_wrap_opencode.py`) — confirms no shared-helper regressions
- [x] **Test authoring for c1 is deferred to ph.3-hardening** — Wave 1 and Wave 2 RED-test descriptions above are the contract ph.3 will materialize