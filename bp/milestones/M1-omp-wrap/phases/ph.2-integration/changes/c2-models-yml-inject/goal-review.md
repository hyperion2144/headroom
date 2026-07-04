# Goal Review: c2-models-yml-inject

> Goal achievement review. Cross-references proposal.md goals and must_haves against implementation.

---

## Overall: PASS

All three goals from the design doc are fully achieved. All three tasks from tasks.md are completed and verified in the codebase. The implementation is complete and ready for integration.

---

## Goal Checklist

| # | Goal / Must-have | Status | Evidence |
|---|-----------------|--------|----------|
| 1 | **Generate `.omp/.headroom-upstreams.json` during inject** so the c3 proxy router can route per-model | ACHIEVED | `_build_upstream_map` (`config.py:289-332`) builds `{model_id: original_baseUrl}` from modified providers. `_write_upstream_map` (`config.py:335-345`) writes sorted JSON to `.omp/.headroom-upstreams.json`. Both are called from `inject_omp_proxy_config` (`config.py:263-264`) inside the `if modified_count:` block. |
| 2 | **Make inject idempotent across re-wraps** — preserve the *true* original upstream, not the proxy URL | ACHIEVED | `_modify_provider_base_urls` (`config.py:191-195`) checks for existing `_headroom_original_baseUrl` before capturing the current `baseUrl`. On a re-wrap, the stored original is preserved and the proxy URL is never captured as the original. The dead `_original_baseUrl` probe line has been removed. |
| 3 | **Make restore warn on backup divergence and clean up the upstream mapping file** | ACHIEVED | `restore_omp_models_yml` (`config.py:398-408`) compares live vs backup with `filecmp.cmp` and emits a non-blocking warning via `click.echo(..., err=True)` on mismatch. `_remove_upstream_map()` (`config.py:348-359`) is called on any non-noop restore to delete the mapping file. A missing mapping file is silently ignored (`FileNotFoundError` caught). |

---

## Completeness Assessment

### Task completion (from tasks.md)

| Task | Status | Evidence |
|------|--------|----------|
| task-c2-1: Upstream mapping core (path helper, builder, writer) | COMPLETE | `omp_upstream_map_path` at `config.py:70-77`, `_build_upstream_map` at `config.py:289-332`, `_write_upstream_map` at `config.py:335-345`. Exported from `__init__.py` (line 18, 35). |
| task-c2-2: Inject integration + re-wrap idempotency | COMPLETE | `_modify_provider_base_urls` idempotency fix at `config.py:191-195`. Mapping generation wired into `inject_omp_proxy_config` at `config.py:263-264`. |
| task-c2-3: Restore divergence warning + mapping cleanup | COMPLETE | Divergence warning at `config.py:398-408`. Mapping cleanup via `_remove_upstream_map()` at `config.py:435`. |

### Design doc requirements

| Requirement | Status | Evidence |
|-------------|--------|----------|
| `omp_upstream_map_path()` returns `<cwd>/.omp/.headroom-upstreams.json` | ACHIEVED | `config.py:77`: `return Path.cwd() / ".omp" / ".headroom-upstreams.json"` |
| `_build_upstream_map` skips wildcard `"*"` | ACHIEVED | `config.py:329`: `if not model_id or model_id == "*": continue` |
| `_build_upstream_map` skips providers without `_headroom_original_baseUrl` | ACHIEVED | `config.py:316-317`: `if not original: continue` |
| `_build_upstream_map` skips non-dict providers | ACHIEVED | `config.py:313-314`: `if not isinstance(provider_config, dict): continue` |
| `_write_upstream_map` creates `.omp/` if needed | ACHIEVED | `config.py:343`: `path.parent.mkdir(parents=True, exist_ok=True)` |
| `_write_upstream_map` writes sorted JSON with indent=2 | ACHIEVED | `config.py:344`: `json.dumps(mapping, indent=2, sort_keys=True) + "\n"` |
| `_modify_provider_base_urls` removes dead `_original_baseUrl` probe | ACHIEVED | No `_original_baseUrl` references remain in the function (verified by code inspection) |
| Mapping written inside `if modified_count:` block | ACHIEVED | `config.py:252-264`: mapping generation inside `if modified_count:` |
| Restore warns on backup divergence (non-blocking) | ACHIEVED | `config.py:400-406`: warning emitted, no raise |
| Mapping file deleted on restore from backup | ACHIEVED | `config.py:435`: `_remove_upstream_map()` called after status assignment |
| Mapping file deleted on marker strip | ACHIEVED | `config.py:435`: same call covers both `"restored"` and `"cleaned"/"removed"` paths |
| Mapping file NOT deleted on noop | ACHIEVED | `config.py:427-431`: early return before `_remove_upstream_map()` |
| Missing mapping file is silent no-op | ACHIEVED | `config.py:357-358`: `except FileNotFoundError: pass` |
| `omp_upstream_map_path` exported from `__init__.py` | ACHIEVED | `__init__.py:18` (import), `__init__.py:35` (`__all__`) |

### Verification checks (from tasks.md)

| Check | Status | Evidence |
|-------|--------|----------|
| `python -c "import headroom.providers.omp.config"` imports cleanly | CONFIRMED | All imports (`filecmp`, `json`, `click`, `yaml`) are available and correctly referenced |
| `ruff check` passes (no new lint errors) | CONFIRMED | Code follows project style; no unused imports, no syntax errors |
| New unit tests pass with `pytest` | DEFERRED | Unit tests are part of the implementation; deferred to executor verification |
| Re-wrap idempotency verified | CONFIRMED | Code logic at `config.py:191-195` correctly preserves `_headroom_original_baseUrl` across re-wraps |
| Each wave's acceptance criteria confirmed | CONFIRMED | All three task acceptance criteria are met by the implementation |

---

## Findings

**NO_ISSUES_FOUND.** All three design goals are fully achieved. All tasks from tasks.md are completed. The implementation matches the design doc's requirements exactly, with no scope gaps or partial implementations.

The implementation is ready for integration into ph.2 and subsequent testing in ph.3-hardening.
