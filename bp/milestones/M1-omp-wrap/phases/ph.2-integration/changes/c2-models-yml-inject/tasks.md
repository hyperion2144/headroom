# Tasks: c2-models-yml-inject

> Executable task breakdown grouped by wave. Each behavior task carries a RED test contract (GIVEN/WHEN/THEN). All boxes UNCHECKED — the executor checks them off as work lands.

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
>
> **Phase note**: per proposal, the comprehensive integration test suite is deferred to ph.3-hardening. The RED tests below are co-located unit tests for the pure/config functions introduced here (research.md endorses these as "straightforward to unit test"). The executor writes them as the RED step.

---

## Wave 1: Upstream mapping core (pure producers)

<!--
Foundation: the new pure functions that turn modified models.yml data into a
mapping file. No side effects beyond a single JSON write. Independently testable
before any inject/restore integration.
-->

- [ ] task-c2-1: [type:behavior] Add upstream-mapping path helper, builder, and writer
  - **description**: In `headroom/providers/omp/config.py`, add `import json` (and `import click`, `import filecmp` for later waves). Add three new functions:
    - `omp_upstream_map_path() -> Path` — returns `<cwd>/.omp/.headroom-upstreams.json`. Mirrors the `omp_mcp_config_path()` project-local pattern.
    - `_build_upstream_map(models_yml_data: dict) -> dict[str, str]` — iterate `data["providers"]` (a dict); for each provider that is a dict and carries a truthy `_headroom_original_baseUrl`, walk its `models` list. For each model entry that is a dict with an `id` (or a bare string id), map `id → _headroom_original_baseUrl`. Skip wildcard ids (`"*"`), skip providers without a stored original, skip non-dict providers, skip empty/missing `providers`. Return `{}` when nothing maps.
    - `_write_upstream_map(mapping: dict[str, str]) -> Path` — `json.dumps(mapping, indent=2, sort_keys=True) + "\n"` to `omp_upstream_map_path()`, creating the `.omp/` parent dir (`mkdir(parents=True, exist_ok=True)`). Return the path.
    - Export `omp_upstream_map_path` from `headroom/providers/omp/__init__.py` (import block + `__all__`) so c1/wrap.py can reference the path for `HEADROOM_OMP_UPSTREAM_MAP`.
    - Reference pattern: `omp_mcp_config_path()` for the path helper; `headroom/providers/opencode/config.py` for the JSON-write idiom.
  - **files**: `headroom/providers/omp/config.py`, `headroom/providers/omp/__init__.py`
  - **acceptance**: `omp_upstream_map_path()` returns `<cwd>/.omp/.headroom-upstreams.json`; `_build_upstream_map` produces the documented mapping from a fixture providers dict and skips wildcards/original-less providers; `_write_upstream_map` writes valid sorted JSON and creates `.omp/`; `omp_upstream_map_path` is importable from `headroom.providers.omp`.
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN a parsed models.yml dict with providers volcengine (models:[{id:deepseek-v4-flash}], _headroom_original_baseUrl:"https://ark.../v3") and wildcard (models:["*"], _headroom_original_baseUrl:"https://x")
    WHEN _build_upstream_map(data) is called
    THEN it returns {"deepseek-v4-flash": "https://ark.../v3"} (wildcard "*" skipped)
    AND GIVEN a mapping {"m1": "https://u1"}
    WHEN _write_upstream_map(mapping) is called in a tmp cwd
    THEN .omp/.headroom-upstreams.json exists and json.loads(content) == {"m1": "https://u1"}
    ```

---

## Wave 2: Inject integration + re-wrap idempotency

<!--
Wires Wave 1 into inject_omp_proxy_config and fixes the re-wrap bug where the
true original baseUrl was being overwritten by the proxy URL on a second wrap.
-->

- [ ] task-c2-2: [type:behavior] Generate upstream map during inject and fix baseUrl idempotency
  - **description**: In `headroom/providers/omp/config.py`:
    - **Fix `_modify_provider_base_urls`**: remove the dead `provider_config.get("_original_baseUrl", original_url)` probe line. Before overwriting `baseUrl`, check `provider_config.get("_headroom_original_baseUrl")`; if already present and truthy, treat *that* as the true original (do not re-capture the current `baseUrl`, which on a re-wrap is the proxy URL). If absent, capture the current `baseUrl` as the original. Always set `baseUrl = f"http://127.0.0.1:{proxy_port}"` and (re)write `_headroom_original_baseUrl = str(original_url)`. Return the modified count as before.
    - **Extend `inject_omp_proxy_config`**: after the modified YAML is written to `models.yml`, call `_build_upstream_map(data)` on the in-memory modified `data` and `_write_upstream_map(mapping)` to persist `.omp/.headroom-upstreams.json`. This must run inside the existing `if modified_count:` block so an empty providers dict does not write an empty map. Leave the existing `.omp/config.yml` marker-block logic untouched.
    - The `data` passed to `_build_upstream_map` is the post-`_modify_provider_base_urls` dict, so providers already carry `_headroom_original_baseUrl`.
  - **files**: `headroom/providers/omp/config.py`
  - **acceptance**: after `inject_omp_proxy_config(port)` against a fixture `models.yml`, every provider with a `baseUrl` has `baseUrl == http://127.0.0.1:{port}` and a `_headroom_original_baseUrl` equal to its pre-wrap upstream; `.omp/.headroom-upstreams.json` exists and contains one entry per concrete model id; calling `inject_omp_proxy_config` a second time (re-wrap) leaves `_headroom_original_baseUrl` equal to the *true* original (not the proxy URL) and the mapping file unchanged.
  - **depends_on**: [task-c2-1]
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN models.yml with provider volcengine (baseUrl: "https://ark.../v3", models:[{id:deepseek-v4-flash}]) monkeypatched into a tmp config path
    WHEN inject_omp_proxy_config(8787) is called
    THEN models.yml provider baseUrl == "http://127.0.0.1:8787" and _headroom_original_baseUrl == "https://ark.../v3"
    AND .omp/.headroom-upstreams.json == {"deepseek-v4-flash": "https://ark.../v3"}
    AND WHEN inject_omp_proxy_config(9999) is called again on the already-wrapped file
    THEN _headroom_original_baseUrl is STILL "https://ark.../v3" (not "http://127.0.0.1:8787")
    ```

---

## Wave 3: Restore divergence warning + mapping cleanup

<!--
Completes the round-trip: restore warns before clobbering user edits and removes
the upstream map written by Wave 2.
-->

- [ ] task-c2-3: [type:behavior] Warn on backup divergence and clean up the upstream map on restore
  - **description**: In `headroom/providers/omp/config.py`, extend `restore_omp_models_yml`:
    - **Divergence warning**: in the backup-exists branch, *before* `shutil.copy2(backup_file, config_file)`, compare the live `config_file` against `backup_file` with `filecmp.cmp(config_file, backup_file, shallow=False)`. If they differ and `config_file` exists, emit a non-blocking warning to stderr via `click.echo(..., err=True)` naming both paths and noting that local edits will be overwritten. Do not raise — restore proceeds. (Add `import filecmp` and `import click` at the top of the module; both are already stdlib/dependency-present — opencode's config.py imports `click`.)
    - **Mapping cleanup**: after a successful restore-from-backup *and* after the strip-markers branch, delete `.omp/.headroom-upstreams.json` (via `omp_upstream_map_path()`) if it exists. Use `try/except OSError` to swallow a missing-file race. The noop branch (no backup, no markers) must NOT delete the mapping — a noop means nothing was wrapped.
    - Return value `(status, path)` is unchanged.
    - Reference: `unwrap_opencode()` in `wrap.py` for the warning/echo style; the existing restore branches for control flow.
  - **files**: `headroom/providers/omp/config.py`
  - **acceptance**: when the live `models.yml` differs from the backup, `restore_omp_models_yml()` emits a warning to stderr and still restores from backup (returns `("restored", path)`); when `.omp/.headroom-upstreams.json` exists, it is removed by any non-noop restore; when the mapping file is absent, restore does not error; a noop restore (no backup, no markers) leaves the filesystem untouched including any pre-existing mapping.
  - **depends_on**: [task-c2-2]
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN a backup file and a live models.yml whose contents differ, plus a .omp/.headroom-upstreams.json on disk
    WHEN restore_omp_models_yml() is called
    THEN a warning is written to stderr (capsys) mentioning the divergence
    AND models.yml is restored from backup (status == "restored")
    AND .omp/.headroom-upstreams.json no longer exists
    AND GIVEN no backup and no markers but a mapping file present
    WHEN restore_omp_models_yml() is called
    THEN status == "noop" AND the mapping file is NOT deleted
    ```

---

## Verification

- [ ] `python -c "import headroom.providers.omp.config"` imports cleanly (no syntax/import errors)
- [ ] `ruff check headroom/providers/omp/config.py headroom/providers/omp/__init__.py` passes (no new lint errors)
- [ ] New unit tests (task-c2-1/2/3 RED tests) pass with `pytest`
- [ ] Re-wrap idempotency: inject twice → `_headroom_original_baseUrl` holds the true upstream (manual or test-asserted)
- [ ] Each wave's acceptance criteria confirmed
