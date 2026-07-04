# Quality Review: c1-basic-wrap

> Code quality audit. Checks for bugs, security issues, conventions, and common AI mistakes.

---

## Overall: PASS

<!-- PASS / FAIL / NEEDS_REVISION
   Verdict rationale: implementation is faithful to the established opencode wrap/unwrap pattern, error handling is inherited from prior helpers, no security or correctness bugs were found. Three minor advisory items are recorded as INFO below and are non-blocking. -->

## Issues

| # | Severity | Category | Location | Description |
|---|----------|----------|----------|-------------|
| 1 | INFO | naming | headroom/cli/wrap.py:181 | Constant named _OMP_INSTALL_URL (https://ohmy.pi). design.md Interface Design referred to it as _OMP_INSTALL_HINT. The implementation-name is the better one (it documents what it stores: a URL). Both names are descriptive; no action needed. |
| 2 | INFO | convention | headroom/cli/wrap.py:5791 | _strip_omp_config_markers reads via path.read_text(encoding=utf-8) directly. The corresponding opencode unwrap reads via the module-level _read_text(path) helper which delegates to fsutil.read_text. The two are functionally equivalent; aligning to _read_text(path) would be a one-line change for consistency. |
| 3 | INFO | efficiency | headroom/cli/wrap.py:5663 | (env, env_vars_display) = build_launch_env(port, os.environ) runs unconditionally even when prepare_only=True so the result is discarded at line 5667. Wasted work is negligible. |
| 4 | INFO | test-coverage | headroom/cli/wrap.py:5628-5854 | The proposal and tasks.md both defer pytest cases to ph.3-hardening per Non-goals (Tests ph.3). Spec/quality reviewers should treat the RED-test descriptions in tasks.md Wave 1 and Wave 2 as the executable acceptance contract. No code action requested in c1. |

(No BLOCKER / MAJOR / MINOR items found.)

## Convention Compliance

| Rule | Status | Note |
|------|--------|------|
| Click decorator stack on omp() unchanged | PASS | Lines 5619-5627. The decorator surface (--port/-p, --no-mcp, --no-proxy, --verbose/-v, hidden --prepare-only, omp_args UNPROCESSED argument) is byte-identical to the pre-c1 stub. |
| Click decorator stack on unwrap_omp() unchanged | PASS | Lines 5802-5806. Single non-hidden option (--no-stop-proxy) preserved exactly. |
| Lazy imports inside command body | PASS | from headroom.mcp_registry import OmpRegistrar and from headroom.providers.omp.runtime import build_launch_env live inside the function bodies (wrap.py:5652-5653, wrap.py:5820). Matches the established opencode/codex/claude wrap idiom. |
| Mirrors opencode unwrap banner | PASS | wrap.py:5822-5826 matches the opencode unwrap layout (wrap.py:5714-5718) verbatim with OMP substituted for OPENCODE. |
| Uses _setup_headroom_mcp(OmpRegistrar(), ...) rather than bespoke MCP wiring | PASS | wrap.py:5661 reuses the generic helper wrap.py:942-974. Acceptance criterion in design.md Alternative 3 explicitly rejects a custom helper. |
| force=True on MCP register | PASS | wrap.py:5661 passes force=True; matches opencode() call site (wrap.py:5548) and accepts MISMATCH-difference overwrite, per design.md Risk Assessment. |
| click.ClickException for missing binary | PASS | wrap.py:5656-5658. Pattern is identical to openclaw wrap (line 5318) and reaches the same error-class used elsewhere in wrap.py. |
| --prepare-only hidden flag preserved | PASS | wrap.py:5626 retains is_flag=True, hidden=True on --prepare-only. |
| Banner order (MCP first, env build, prepare_only short-circuit, _launch_tool) | PASS | wrap.py:5655-5678. Matches design.md Data Flow "Wrap -- happy path" steps 2-5 exactly. |
| Unwrap order (banner, restore models.yml, strip project config, unregister MCP, completion line, proxy stop) | PASS | wrap.py:5822-5854. Matches design.md Data Flow "Unwrap -- happy path" steps 1-6. |
| Idempotency: second consecutive unwrap omp is a silent no-op | PASS | wrap.py:5852 gates _stop_local_proxy_for_unwrap behind status != "noop". |
| Type hints | PASS | omp() body types match the pre-c1 stub; _strip_omp_config_markers(path) and unwrap_omp(port, no_stop_proxy) both type-annotate explicitly. |
| No NotImplementedError in either function body | PASS | grep confirms zero matches in headroom/cli/wrap.py after the three commits. Acceptance criterion satisfied. |
| No new module-level top-level imports added to wrap.py | PASS | Diff scan shows only _OMP_INSTALL_URL added; all OMP dependencies are lazy. |

## Findings

1. NO_ISSUES_FOUND for security. No untrusted input is read directly from the command line; port flows through click.IntRange; no shell construction; no filesystem traversal beyond Path.cwd() / .omp (a project-local fixed path).

2. NO_ISSUES_FOUND for AI-mistake patterns. Every helper referenced is exported by an existing module and shows up in-tree (verified by grep/read). No over-abstraction. Error handling inherited from prior helpers. _OMP_INSTALL_URL is the only hard-coded value and matches the convention used by openclaw wrap.

3. NO_ISSUES_FOUND for shared-helper regressions. The change is additive inside omp() and unwrap_omp() bodies plus one new helper. Opencode wrap (wrap.py:5489-5611) and opencode unwrap (wrap.py:5699-5769) byte-blocks are untouched by the c1 commits.

4. INFO (_OMP_INSTALL_URL naming vs design.md _OMP_INSTALL_HINT): documented above. No action needed.

5. INFO (_strip_omp_config_markers reads via path.read_text rather than _read_text): flagged for consistency only.

6. INFO (build_launch_env is called even on --prepare-only): wasted compute is negligible; flag retained to document the trade-off.

## Pass Conditions

- verdict: PASS
- BLOCKER / MAJOR count: 0
- MINOR count: 0
- INFO count: 4
- Action requested: none. The orchestrator may archive c1; the INFO items can be revisited in a follow-up cleanup PR or in ph.3 if pytest scaffolding benefits from the simpler file-read idiom.
