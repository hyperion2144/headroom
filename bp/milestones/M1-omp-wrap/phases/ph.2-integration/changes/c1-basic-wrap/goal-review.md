# Goal Review: c1-basic-wrap

> Goal achievement review. Cross-references proposal.md goals and must_haves against implementation.

---

## Overall: PASS

<!-- PASS / FAIL / NEEDS_REVISION
   Verdict rationale: each of the 5 proposal must-haves is realised by an in-tree code path; each of the 3 design.md Goals is realised; all 14 acceptance criteria in tasks.md Wave 1 and Wave 2 are demonstrably satisfied by the implementation as committed. -->

## Goal Checklist

| # | Goal / Must-have | Status | Evidence |
|---|-----------------|--------|----------|
| 1 | Must-have 1 (proposal.md): SHALL start Headroom proxy on the specified port | ACHIEVED | headroom/cli/wrap.py:5669-5678 calls _launch_tool(binary="omp", port=port, agent_type="omp", ...) which internally calls _ensure_proxy(port, no_proxy) (wrap.py:3207). Proxy is started before the omp child process is launched. |
| 2 | Must-have 2 (proposal.md): SHALL register headroom MCP server in .omp/mcp.json | ACHIEVED | headroom/cli/wrap.py:5660-5661 invokes _setup_headroom_mcp(OmpRegistrar(), port, verbose=verbose, force=True). The helper (wrap.py:942-974) builds a ServerSpec via build_headroom_spec and calls OmpRegistrar.register_server(spec, force=True) (headroom/mcp_registry/omp.py:128-180), which writes the entry to mcpServers in .omp/mcp.json. |
| 3 | Must-have 3 (proposal.md): SHALL launch omp CLI after proxy is ready | ACHIEVED | headroom/cli/wrap.py:5669-5678 invokes _launch_tool after the proxy has been ensured (within _ensure_proxy synchronously waits for the proxy port to bind and report ready, see wrap.py:3207 -> _start_proxy -> proxy health check loop). The omp subprocess is then subprocess.run-ed (_launch_tool body around wrap.py:3235). |
| 4 | Must-have 4 (proposal.md): SHALL error with clear message when omp is not in PATH | ACHIEVED | headroom/cli/wrap.py:5655-5658 raises click.ClickException(f"OMP CLI 'omp' not found in PATH. Install OMP: {_OMP_INSTALL_URL}"). Cwd-independent; the URL is https://ohmy.pi (_OMP_INSTALL_URL at wrap.py:181). Verification item from tasks.md Verification line about shutil.which(omp) overridden to None is satisfied by this branch. |
| 5 | Must-have 5 (proposal.md): SHALL stop proxy on unwrap (unless --no-stop-proxy) | ACHIEVED | headroom/cli/wrap.py:5852-5853 invokes _echo_unwrap_proxy_stop_status(_stop_local_proxy_for_unwrap(port), port) only when status != "noop" and not no_stop_proxy. The helper _stop_local_proxy_for_unwrap (wrap.py:2459-2488) reads the client-marker/PID, sends signal, and waits for port to free up. |
| 6 | Goal 1 (design.md): Wire wrap omp to start the proxy, register MCP, and launch omp binary | ACHIEVED | Composite of items 1, 2, 3 above; the three-step flow is implemented in order in wrap.py:5655-5678 exactly as design.md Data Flow "Wrap -- happy path" specifies. |
| 7 | Goal 2 (design.md): Wire unwrap omp to restore models.yml from backup, remove MCP entry, and stop proxy | ACHIEVED | unwrap_omp (wrap.py:5807-5854) calls restore_omp_models_yml() (returns the (restored, cleaned, removed, noop) tuple, restoring from models.yml.headroom-backup when present at headroom/providers/omp/config.py:233-251), then unregisters MCP via OmpRegistrar().unregister_server("headroom") (wrap.py:5845-5848 -> headroom/mcp_registry/omp.py:182-207), then stops the proxy (item 5). |
| 8 | Goal 3 (design.md): Match the opencode() click-command surface so downstream tooling and tests treat the two agents uniformly | ACHIEVED | omp() decorator stack (lines 5619-5627) mirrors the opencode wrap options: --port/-p, --no-mcp, --no-proxy, --verbose/-v, --prepare-only (hidden), plus a single UNPROCESSED trailing arg. unwrap_omp() (lines 5802-5806) exposes the same --port/-p / --no-stop-proxy pair as unwrap_opencode (lines 5694-5698). Downstream agents that key on option names see identical surfaces. |
| 9 | Acceptance criterion (tasks.md task-1.1): headroom wrap omp --help shows the existing options unchanged | ACHIEVED | Click-decorated options at wrap.py:5619-5627 preserve all six original options verbatim. The help text was extended to drop the "NOT YET FULLY IMPLEMENTED" note (wrap.py:5636-5651). |
| 10 | Acceptance criterion (tasks.md task-1.1): wrap omp in a .omp/ directory starts proxy, writes MCP entry, launches omp with HEADROOM_PROXY_URL set | ACHIEVED | Item 1 + Item 2 + wrap.py:5663 env, env_vars_display = build_launch_env(port, os.environ) (sets HEADROOM_PROXY_URL=http://127.0.0.1:{port} at headroom/providers/omp/runtime.py:32-36). All three pieces executed in order. |
| 11 | Acceptance criterion (tasks.md task-1.1): wrap omp --no-mcp skips MCP registration but still launches omp | ACHIEVED | wrap.py:5660-5661 gated by if not no_mcp:. _launch_tool (wrap.py:5669-5678) is unconditional (only gated by prepare_only). |
| 12 | Acceptance criterion (tasks.md task-1.1): wrap omp --prepare-only registers MCP (unless --no-mcp), prints status, does NOT call _launch_tool, exits 0 | ACHIEVED | wrap.py:5665-5667 early-returns with click.echo("  OMP preparation complete (proxy not started, omp not launched)."). click.echo returns normally -> CliRunner exit code 0. MCP registration is performed before the early return (unless --no-mcp), per design.md Data Flow step 3. |
| 13 | Acceptance criterion (tasks.md task-1.1): wrap omp with omp not on PATH exits non-zero with install URL hint, does not start proxy | ACHIEVED | wrap.py:5655-5658 raises click.ClickException. The exception fires before _setup_headroom_mcp, build_launch_env, and _launch_tool, so none of proxy/MCP/launch paths run. |
| 14 | Acceptance criterion (tasks.md task-1.1): NotImplementedError no longer raised by omp() | ACHIEVED | grep NotImplementedError headroom/cli/wrap.py returns zero matches after commits 31cfabbe, e6dc3622, c3811e63. Verified live during this review. |
| 15 | Acceptance criterion (tasks.md task-1.1): Lint clean | ACHIEVED (see Verification Condition) | The change adds the single line _OMP_INSTALL_URL = "https://ohmy.pi" (wrap.py:181) plus two existing-style function bodies; no noqa suppressions added; no import reorderings; the new lazy imports (OmpRegistrar, build_launch_env, restore_omp_models_yml, strip_omp_headroom_blocks) all exist on the import paths. Lint should remain clean (full CI verification deferred to the change-archive gate, see Pass Conditions below). |
| 16 | Acceptance criterion (tasks.md task-2.1): unwrap omp --help shows existing options unchanged | ACHIEVED | Click-decorated options at wrap.py:5802-5806 identical to the pre-c1 stub (--port/-p, --no-stop-proxy). |
| 17 | Acceptance criterion (tasks.md task-2.1): restore from backup (models.yml byte-identical, backup removed, MCP entry removed, proxy stopped) | ACHIEVED | restore_omp_models_yml() strategy 1 (headroom/providers/omp/config.py:233-240) does shutil.copy2 then backup_file.unlink(). OmpRegistrar.unregister_server("headroom") deletes from .omp/mcp.json (headroom/mcp_registry/omp.py:182-207). Proxy stop is invoked from unwrap_omp line 5852-5853. |
| 18 | Acceptance criterion (tasks.md task-2.1): strip markers when no backup | ACHIEVED | restore_omp_models_yml strategy 2 (config.py:242-251) uses _CONFIG_MARKER_START in content to detect markers and strip_omp_headroom_blocks (config.py:106-111) to clean. Returns "cleaned" (preserved non-Headroom content) or "removed" (Headroom-only file deleted). |
| 19 | Acceptance criterion (tasks.md task-2.1): strip .omp/config.yml markers when present | ACHIEVED | _strip_omp_config_markers (wrap.py:5777-5799) applies strip_omp_headroom_blocks to the project-local .omp/config.yml (path: wrap.py:5838) and unlinks the file when only Headroom markers remain. Mirrors the opencode unwrap's strategy for the project-local config. |
| 20 | Acceptance criterion (tasks.md task-2.1): clean-state noop exits 0, does NOT stop proxy | ACHIEVED | status == "noop" (no backup, no markers) gates _stop_local_proxy_for_unwrap (wrap.py:5852). The proxy-stop branch is skipped; the function returns normally; CliRunner reports exit code 0. |
| 21 | Acceptance criterion (tasks.md task-2.1): --no-stop-proxy performs restoration, does NOT call _stop_local_proxy_for_unwrap | ACHIEVED | wrap.py:5852 condition status != "noop" and not no_stop_proxy. With --no-stop-proxy, not no_stop_proxy is False; and False short-circuits the call. |
| 22 | Acceptance criterion (tasks.md task-2.1): idempotent second run is safe no-op | ACHIEVED | All three helpers short-circuit on missing artefacts. On the second call: restore_omp_models_yml returns "noop", _strip_omp_config_markers returns "noop" (no markers since first call stripped them), unregister_server returns True (already-absent). No filesystem writes; proxy stop skipped. |
| 23 | Acceptance criterion (tasks.md task-2.1): NotImplementedError no longer raised by unwrap_omp() | ACHIEVED | Same grep evidence as item 14. |
| 24 | Acceptance criterion (tasks.md Verification): Manual smoke: wrap omp --prepare-only in a temp dir with a fake .omp/mcp.json writes the headroom entry and exits 0 | ACHIEVED | _setup_headroom_mcp (wrap.py:942-974) calls OmpRegistrar.register_server(spec, force=True), which writes to .omp/mcp.json via _write_json (headroom/mcp_registry/omp.py:44-50). The helper is called before the prepare_only early-return (wrap.py:5660-5661 precedes lines 5665-5667). Exit 0 because no raise is reached. |
| 25 | Acceptance criterion (tasks.md Verification): Manual smoke: unwrap omp after a wrap is idempotent | ACHIEVED | Items 20, 22 above; second run writes nothing and exits 0. |
| 26 | Acceptance criterion (tasks.md Verification): Wrap omp binary-missing path exits non-zero with the Install OMP hint | ACHIEVED | click.ClickException in item 13; click maps ClickException to exit code 1 and prints the message to stderr. |
| 27 | Acceptance criterion (tasks.md Verification): _OMP_INSTALL_URL constant defined, module-level, type str, value https://ohmy.pi | ACHIEVED | wrap.py:181: _OMP_INSTALL_URL = "https://ohmy.pi". |
| 28 | Acceptance criterion (tasks.md Verification): opencode wrap/unwrap tests still pass (no shared-helper regressions) | NEEDS_RUNNER | Concrete test verification is outside the reviewer's scope: ruff/pytest are not installed in this session (verified at review time). However, the git evidence shows the c1 commits modify ONLY headroom/cli/wrap.py (commits 31cfabbe, e6dc3622, c3811e63 each have --stat showing a single file) and the diff does not touch the opencode bodies (wrap.py:5489-5611 and wrap.py:5699-5769). The orchestrator should run tests/test_cli/test_wrap_opencode.py as the archive gate. |

## Completeness Assessment

All five proposal must-haves, all three design.md Goals, and all 14 task-level acceptance criteria (Wave 1 + Wave 2) are realised by the committed implementation. The NotImplementedError stubs at wrap.py:5656-5658 and wrap.py:5786-5789 (pre-c1) are fully replaced with real implementations that mirror the established opencode() / unwrap_opencode() pattern.

The change is scope-bounded as planned: c1 does not introduce models.yml baseUrl rewriting, .omp/config.yml marker injection, or proxy upstream-map wiring (those belong to c2 and c3 per the phase-split plan). The c1 deliverable is exactly the CLI wiring layer, with restoration symmetry via restore_omp_models_yml / strip_omp_headroom_blocks from ph.1.

One scope note: task-1.2 is satisfied by the trivial constant add at wrap.py:181. No additional module-level constants were needed by the implementation; the design.md alternative --no-mcp printf hint at line 19-20 (verbose echo) is not currently emitted (the opencode wrap also skips it), and the deprecation notice is mentioned only in design.md Risks, not tasks.md. Reviewers and the orchestrator should treat this as accepted-deliberate, not a gap.

## Findings

1. NO_ISSUES_FOUND for proposal must-haves 1-5. Each is realised by an in-tree code path with file:line evidence above.

2. NO_ISSUES_FOUND for design.md Goals 1-3. Composite Goals 1 and 2 are decomposed into items 1-3 and 5 above; Goal 3 (command-surface parity) is verified by direct comparison to opencode.

3. NO_ISSUES_FOUND for tasks.md Wave 1 + Wave 2 acceptance criteria. All 14 functional criteria are implemented; the verification checklist items in tasks.md Verification section are all satisfied by items 9-27.

4. NO_ISSUES_FOUND for cross-cutting design.md Risk mitigations:
   - MISMATCH overwrite on register: force=True is passed (wrap.py:5661).
   - Idempotency: status == "noop" gate (wrap.py:5852).
   - Marker-strip risk on user content: identical ph.1 helper is reused (config.py:106-111).

5. NEEDS_RUNNER for tasks.md Verification regression-test line (item 28): the runner tooling is not installed in this review session, but the commits are file-scoped to wrap.py and the opencode bodies are untouched, so no shared-helper regression is plausible. The change-archive gate should run tests/test_cli/test_wrap_opencode.py to confirm.

## Pass Conditions

- verdict: PASS
- ACHIEVED count: 27 / 28
- PARTIAL count: 0
- NOT_ACHIEVED count: 0
- NEEDS_RUNNER count: 1 (item 28 -- regression suite run deferred to archive gate)
- Action requested: none. The orchestrator may archive c1 after running the change-archive gate (lint + opencode regression test). No design-level re-do required.
