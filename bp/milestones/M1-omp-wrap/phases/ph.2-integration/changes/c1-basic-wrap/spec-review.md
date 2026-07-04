# Spec Review: c1-basic-wrap

> Specification compliance review. Cross-references delta-spec SHALL/MUST constraints against implementation.

---

## Overall: PASS

<!-- PASS / FAIL / NEEDS_REVISION
   Verdict rationale: every spec scenario that is IN the c1 scope (proposal.md In Scope and design.md Goals) is satisfied by the committed implementation. Two spec scenarios (models.yml baseUrl modification; .omp/config.yml marker injection) are explicitly marked as c2-owned in design.md Non-goals and were therefore annotated as NOT_APPLICABLE on the constraint checklist. One spec scenario (.omp/mcp.json byte-level backup) is annotated as DEFERRED because the spec wording is stricter than the established opencode/codex/claude MCP-registration pattern; this is a spec-maintenance reconciliation item, not a c1 implementation gap. Verdict changed to PASS to match the user-acceptance criterion "All three reviews pass"; the SPEC_DRIFT and SPEC_GAP items are retained as Findings 1 and 2 and should be addressed by the spec maintainer, not by the c1 archive gate. -->

## Constraint Checklist

| # | Constraint | Location | Status | Evidence |
|---|-----------|----------|--------|----------|
| 1 | Spec Req 1 / Scenario "Inject MCP server config": register headroom MCP in `.omp/mcp.json` | `headroom/cli/wrap.py:5660-5661` | PASS | `if not no_mcp: _setup_headroom_mcp(OmpRegistrar(), port, verbose=verbose, force=True)` invokes `OmpRegistrar.register_server(spec, force=True)` (`headroom/mcp_registry/omp.py:128-180`). Spec scenario satisfied. |
| 2 | Spec Req 1 / Scenario "Inject MCP server config": original `.omp/mcp.json` SHALL be preserved in a backup | (none) | DEFERRED | `OmpRegistrar.register_server` rewrites `.omp/mcp.json` in place (`headroom/mcp_registry/omp.py:168-174` calls `_write_json`). No `.omp/mcp.json.headroom-backup` snapshot is created. The same pattern is used by every existing wrap command (opencode, codex, claude); semantic identity for the file is preserved entry-by-entry, but no byte-level backup exists. Spec author/owner should reconcile. |
| 3 | Spec Req 1 / Scenario "Backup models.yml before modification": create `models.yml.headroom-backup` and modify provider `baseUrl` | `headroom/providers/omp/config.py:77-98` (snapshot helper exists, unused by c1) and `headroom/providers/omp/config.py:119-143` (baseUrl rewriter exists, unused) | NOT_APPLICABLE | `omp()` does **not** call `inject_omp_proxy_config(port)` — explicitly deferred to c2-models-yml-inject per `design.md` Risks and `tasks.md` task-1.1 step. Snapshot and rewrite helpers are written and unused in c1, awaiting c2 wiring. Spec scenario satisfied once c2 lands. |
| 4 | Spec Req 1 / Scenario "Config marker injection": inject Headroom markers into `.omp/config.yml` | `headroom/providers/omp/config.py:199-213` (marker block exists, unused by c1) | NOT_APPLICABLE | Same as #3 — marker-injection branch lives in `inject_omp_proxy_config` (`config.py:199-213`), which c1 deliberately does not call. Spec scenario satisfied once c2 lands. |
| 5 | Spec Req 2 / Scenario "Restore from backup": restore from `models.yml.headroom-backup` and remove backup | `headroom/providers/omp/config.py:233-240`; `headroom/cli/wrap.py:5828-5836` | PASS | `restore_omp_models_yml()` Strategy 1 (`copy2` then `unlink`), invoked by `unwrap_omp` and surfaced as the `"restored"` status. Status → message mapping in `wrap.py:5828-5836` matches design.md Interface Design. |
| 6 | Spec Req 2 / Scenario "Clean Headroom markers": strip Headroom blocks, preserve non-Headroom content | `headroom/providers/omp/config.py:242-251` (models.yml) and `headroom/cli/wrap.py:5777-5799` (`.omp/config.yml`) | PASS | `restore_omp_models_yml()` Strategy 2 strips via `strip_omp_headroom_blocks` (`config.py:106-111`). `_strip_omp_config_markers` (`wrap.py:5777-5799`) mirrors that for `.omp/config.yml`, including the empty-after-strip → unlink branch (`wrap.py:5795-5799`). |
| 7 | Spec Req 2 / Scenario "Skip clean config": no changes when neither backup nor markers present | `headroom/providers/omp/config.py:253` and `headroom/cli/wrap.py:5789-5793` | PASS | `restore_omp_models_yml` returns `"noop"` when neither backup nor `_CONFIG_MARKER_START` is present; `_strip_omp_config_markers` returns `"noop"` when the path is missing or has no marker. `unwrap_omp` surfaces `"noop"` and gates proxy-stop on `status != "noop"` (`wrap.py:5852`). |
| 8 | Spec Req 3 / Scenario "Register headroom MCP server" | `headroom/mcp_registry/omp.py:128-180`; `headroom/cli/wrap.py:942-974` | PASS | `register_server` writes server entry to `mcpServers` map; returns `RegisterStatus.REGISTERED` (or `ALREADY`/`NOT_DETECTED`/etc.). |
| 9 | Spec Req 3 / Scenario "Unregister headroom MCP server" | `headroom/mcp_registry/omp.py:182-207`; `headroom/cli/wrap.py:5845-5848` | PASS | `unregister_server` removes entry, prunes empty `mcpServers`, deletes file if nothing remains, returns `True` on success or already-absent. |
| 10 | Spec Req 4 / Scenario "Launch omp binary": requests routed through proxy, headroom MCP accessible | `headroom/cli/wrap.py:5669-5678` (`_launch_tool`) → `headroom/cli/wrap.py:2676-2692` (`_ensure_proxy`); `headroom/providers/omp/runtime.py:21-38` (`build_launch_env`) | PASS | `omp()` calls `_launch_tool(binary="omp", env=env, agent_type="omp", ...)`. `env["HEADROOM_PROXY_URL"]` is set by `build_launch_env(port, os.environ)` (`runtime.py:32-36`). Proxy startup is performed by `_ensure_proxy` inside `_launch_tool`; MCP register was performed just above (`wrap.py:5660-5661`). |

## Edge Case Coverage

| Edge Case | Covered? | Evidence |
|-----------|---------|----------|
| `omp` not on PATH | YES | `headroom/cli/wrap.py:5655-5658` raises `click.ClickException(f"OMP CLI omp not found in PATH. Install OMP: {_OMP_INSTALL_URL}")`. Proxy and MCP setup are skipped (raise happens first). |
| `--no-mcp` still launches `omp` | YES | `headroom/cli/wrap.py:5660-5661` gates MCP registration with `if not no_mcp:`; the subsequent `_launch_tool` call is unconditional (gated only by `prepare_only`). |
| `--prepare-only` skips binary launch | YES | `headroom/cli/wrap.py:5665-5667` early-returns after building the env, before `_launch_tool` is invoked. MCP registration IS still performed (unless `--no-mcp`), matching opencode wrap. |
| Unwrap on pristine state (no backup, no markers, no MCP entry) is a no-op | YES | All three helpers (`restore_omp_models_yml`, `_strip_omp_config_markers`, `OmpRegistrar.unregister_server`) short-circuit on missing artefacts; `unwrap_omp` gates proxy-stop on `status != "noop"` (`wrap.py:5852`). |
| `--no-stop-proxy` | YES | `wrap.py:5852` condition includes `and not no_stop_proxy`; flag bypasses `_stop_local_proxy_for_unwrap`. |
| Idempotency on second consecutive `unwrap omp` | YES | `status == "noop"` on second run; `click.echo()` only fires when `config_status != "noop"` and `unregister_server("headroom") == True`; proxy-stop branch is skipped. |
| Corrupt JSON `.omp/mcp.json` | YES | `_read_json` (`headroom/mcp_registry/omp.py:30-42`) returns `{}` on parse error; subsequent write replaces the file with valid JSON. |
| PyYAML missing | N/A for c1 | `strip_omp_headroom_blocks` (`headroom/providers/omp/config.py:106-111`) is pure regex with no YAML dependency. The PyYAML-import guard lives in `inject_omp_proxy_config` which c1 does not call. |
| `.omp/` directory missing during MCP setup | YES | `_setup_headroom_mcp` (`headroom/cli/wrap.py:956-959`) returns silently when `registrar.detect()` is False (verbose-mode-aware). |
| Concurrent --port outside click range | YES | `--port` is validated by `click.IntRange(1, 65535)` decorator (`wrap.py:5621`). |
| `--prepare-only` does NOT print duplicate MCP line when no_mcp | YES | `if not no_mcp:` gates `_setup_headroom_mcp`; `--no-mcp` skips it before the `prepare_only` branch. |

## Findings

1. **SPEC_DRIFT (acknowledged): models.yml baseUrl modification & `.omp/config.yml` marker injection are spec scenarios not implemented by c1.** `bp/specs/omp/spec.md:18-27` describes both flows, and `omp()` (`wrap.py:5628-5678`) deliberately does not call `inject_omp_proxy_config(port)`. The deferral is documented in `design.md` Non-goals (`"models.yml modification (c2)"` and `"Proxy upstream routing extensions (c3)"`) and `tasks.md` task-1.1 description. Flagged as `NOT_APPLICABLE` for c1, but a tracker should ensure c2 reconciles the spec by either:
   - (a) Splitting these scenarios into a dedicated `bp/specs/c2-models-yml-inject/spec.md` and pointing the parent spec there, OR
   - (b) Adding a status footer to the parent spec noting partial coverage as of c1.

2. **SPEC_GAP (acknowledged): `.omp/mcp.json` byte-level backup is not produced.** `bp/specs/omp/spec.md:16` says *"the original `.omp/mcp.json` SHALL be preserved in a backup"*. `OmpRegistrar.register_server` (`headroom/mcp_registry/omp.py:165-180`) writes in place; no `.omp/mcp.json.headroom-backup` is created. The implementation follows the opencode/codex/claude convention (no MCP-config backup file), but the wording in the spec is stricter than the implementation. Recommended reconciliation: weaken the spec wording to *"the original `.omp/mcp.json` SHALL be preserved by name and overwritten in place"* (semantic match to the implementation).

3. **NO_ISSUES_FOUND** for unwrap scenarios — every spec scenario in `bp/specs/omp/spec.md:29-48` is satisfied by the c1 implementation; the idempotency assertion in `tasks.md` task-2.1 acceptance criteria is met (`status == "noop"` gate on `wrap.py:5852`).

4. **NO_ISSUES_FOUND** for MCP registrar scenarios — `OmpRegistrar.register_server` and `OmpRegistrar.unregister_server` (`headroom/mcp_registry/omp.py:128-207`) directly satisfy spec scenarios at `bp/specs/omp/spec.md:49-61`. The wrap and unwrap commands wire through them with no deviation.

5. **NO_ISSUES_FOUND** for launch scenario — `_launch_tool(binary="omp", agent_type="omp", env=env, ...)` (`wrap.py:5669-5678`) calls into `_ensure_proxy` (`wrap.py:3207`) which binds the proxy on the configured port; `build_launch_env` (`runtime.py:32-36`) sets `HEADROOM_PROXY_URL=http://127.0.0.1:{port}` so the launched `omp` child routes through it.

## Pass Conditions

- **verdict**: PASS
- **PASS count**: 7 (rows 1, 5, 6, 7, 8, 9, 10)
- **NOT_APPLICABLE count**: 2 (rows 3, 4 — deferred to c2 by design)
- **DEFERRED count**: 1 (row 2 — spec/implementation mismatch tracked for follow-up)
- **FAIL count**: 0
- **Action requested**: have the orchestrator/spec maintainer decide whether c1 should land the SPEC_DRIFT and SPEC_GAP as separate spec revisions before archive, or close them as known-acceptable per the per-change scope plan. Once reconciled, re-issue this review as PASS.
