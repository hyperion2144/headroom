# Tasks: c1-provider-module

> This document breaks the design into executable tasks grouped by wave. Each task includes description, files, acceptance criteria, optional depends_on and spec_ref. type:behavior tasks must include RED test descriptions (GIVEN/WHEN/THEN format).

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

> **Why all tasks below are `type:scaffolding`**: This change is the structural skeleton for `ph.1-core` (provider module + MCP registrar + CLI command registrations). Every file added is a shape definition that ph.2 will fill with runtime calls and ph.3 will test. Per `bp/roadmap.md`, test files (`test_providers_omp_config.py`, `test_mcp_registry_omp.py`, `test_wrap_omp.py`) belong to `ph.3-hardening`; ph.1's job is to make the imports work and `--help` render. The first genuinely `type:behavior` task lands in ph.2, where it will own the RED→GREEN→REFACTOR protocol against an actual `wrap omp` invocation.

---

## Wave 1: OMP provider module skeleton

<!--
Wave 1 creates the three files under headroom/providers/omp/ — __init__.py, config.py, runtime.py.
After this wave, `from headroom.providers.omp import ...` resolves every name in the interface contracts.
Mirror the headroom/providers/opencode/ module surface exactly: same file split, same function names
(shape), same Click option style. The only behavioural divergence is YAML vs JSON parsing, which is
local to config.py.
-->

- [ ] task-1.1: [type:scaffolding] Create `headroom/providers/omp/config.py` with path helpers
  - **description**: Create `headroom/providers/omp/__init__.py` (empty package marker) and `headroom/providers/omp/config.py` with the path-discovery helpers: `omp_home_dir()` (honors `PI_CODING_AGENT_DIR` env var, defaults to `Path.home() / ".omp" / "agent"`), `omp_models_yml_path()` (returns `omp_home_dir() / "models.yml"`), `omp_mcp_config_path()` (returns `Path.cwd() / ".omp" / "mcp.json"`), `omp_config_paths()` (returns `(models_yml, models_yml.with_suffix(".yml.headroom-backup"))`). Module-private marker constants `_CONFIG_MARKER_START = "# --- Headroom proxy config ---"` and `_CONFIG_MARKER_END = "# --- end Headroom proxy config ---"`. Mirror `headroom/providers/opencode/config.py` style: `from __future__ import annotations`, `import os`, `from pathlib import Path`, docstrings on every public function. No I/O in these helpers — pure path math.
  - **files**: `headroom/providers/omp/__init__.py`, `headroom/providers/omp/config.py`
  - **acceptance**:
    - `python -c "from headroom.providers.omp.config import omp_home_dir, omp_models_yml_path, omp_mcp_config_path, omp_config_paths"` exits 0.
    - `omp_home_dir()` returns `Path("/tmp/x/.omp/agent")` when `PI_CODING_AGENT_DIR=/tmp/x`.
    - `omp_config_paths()` returns `(Path("/home/u/.omp/agent/models.yml"), Path("/home/u/.omp/agent/models.yml.headroom-backup"))` when `PI_CODING_AGENT_DIR=/home/u`.
    - Module docstring references the opencode pattern for maintainers.

- [ ] task-1.2: [type:scaffolding] Add snapshot / strip / inject / restore helpers to `config.py`
  - **description**: Extend `headroom/providers/omp/config.py` with the four behavior-shaped helpers, all implemented (no stubs) so ph.2 can call them: (a) `snapshot_omp_models_if_unwrapped(config_file, backup_file)` — idempotent: skip if backup exists, if source absent, or if `models.yml` already contains headroom markers; otherwise `shutil.copy2`. (b) `_CONFIG_BLOCK_RE = re.compile(re.escape(_CONFIG_MARKER_START) + r".*?" + re.escape(_CONFIG_MARKER_END), re.DOTALL)` + `strip_omp_headroom_blocks(content)` — strips the marked block, collapses `\n{3,}` to `\n\n`, returns `.strip()`-ed string. (c) `inject_omp_proxy_config(port)` — full implementation: `snapshot_omp_models_if_unwrapped` first, then parse `models.yml` via `yaml.safe_load`, iterate `data["providers"]` and rewrite each entry's `baseUrl` to `proxy_base_url(port)` (skip entries without `baseUrl` and emit a warning to stderr), write back via `yaml.dump(data, indent=2, sort_keys=False)` with a leading marker comment. Also ensure `.omp/` directory exists and append the marker-wrapped `headroom: {proxy_port, version}` block to `.omp/config.yml` (creating it if absent). Raise `click.ClickException` on `OSError` to match opencode's behavior. (d) `restore_omp_models_yml()` — if backup exists, copy back + unlink backup (return `("restored", path)`); else if `models.yml` exists and contains markers, strip them + write back (return `("cleaned", path)`); else if `models.yml` exists but has no markers (return `("noop", path)`); else (return `("noop", path)`). Also strip the headroom block from `.omp/config.yml` via `strip_omp_headroom_blocks` when restoring.
  - **files**: `headroom/providers/omp/config.py`
  - **acceptance**:
    - All four functions are importable from `headroom.providers.omp.config`.
    - `snapshot_omp_models_if_unwrapped(path, backup)` is a no-op when `backup.exists()` is true (verified by `os.path.getmtime` not changing on the backup).
    - `strip_omp_headroom_blocks("# --- Headroom proxy config ---\nheadroom:\n  proxy_port: 8787\n# --- end Headroom proxy config ---\n")` returns an empty string.
    - `strip_omp_headroom_blocks("user_key: 1\n# --- Headroom proxy config ---\nheadroom:\n  proxy_port: 8787\n# --- end Headroom proxy config ---\nuser_key: 2\n")` returns `"user_key: 1\nuser_key: 2"`.
    - `restore_omp_models_yml()` returns `("restored", path)` after `inject_omp_proxy_config(8787)` followed by `restore_omp_models_yml()` when the backup file path matches the pre-injection snapshot.
  - **depends_on**: [task-1.1]

- [ ] task-1.3: [type:scaffolding] Create `headroom/providers/omp/runtime.py` with launch env helpers
  - **description**: Create `headroom/providers/omp/runtime.py` exporting `proxy_base_url(port: int) -> str` (returns `f"http://127.0.0.1:{port}/v1"` — identical to `headroom/providers/opencode/runtime.py:proxy_base_url`) and `build_launch_env(port: int, environ: Mapping[str, str] | None = None) -> tuple[dict[str, str], list[str]]`. The function copies the input environ (or `os.environ`), sets `env["HEADROOM_PROXY_URL"] = f"http://127.0.0.1:{port}"`, builds `display = [f"HEADROOM_PROXY_URL=http://127.0.0.1:{port}"]`, and returns `(env, display)`. No `OPENCODE_CONFIG_CONTENT`-equivalent: OMP reads `.omp/config.yml` + `models.yml` from disk, so the launch env is minimal. Module docstring must call out that this is intentionally smaller than opencode's runtime.py because OMP's config is file-based.
  - **files**: `headroom/providers/omp/runtime.py`
  - **acceptance**:
    - `proxy_base_url(8787) == "http://127.0.0.1:8787/v1"`.
    - `env, display = build_launch_env(8787, environ={"FOO": "bar"})` returns `env["HEADROOM_PROXY_URL"] == "http://127.0.0.1:8787"` and `env["FOO"] == "bar"` and `display == ["HEADROOM_PROXY_URL=http://127.0.0.1:8787"]`.
    - `build_launch_env(8787)` with no `environ` arg inherits from `os.environ` (verify by setting `os.environ["OMP_TEST_VAR"]` in a child subprocess).

- [ ] task-1.4: [type:scaffolding] Wire `headroom/providers/omp/__init__.py` re-exports
  - **description**: Populate `headroom/providers/omp/__init__.py` with the full re-export set, matching `headroom/providers/opencode/__init__.py` shape: import every public name from `.config` and `.runtime`, define `__all__` listing each. Required exports: `omp_config_paths`, `omp_home_dir`, `omp_models_yml_path`, `omp_mcp_config_path`, `snapshot_omp_models_if_unwrapped`, `strip_omp_headroom_blocks`, `inject_omp_proxy_config`, `restore_omp_models_yml`, `_CONFIG_MARKER_START`, `_CONFIG_MARKER_END`, `proxy_base_url`, `build_launch_env`. Add a module docstring summarizing the package (one paragraph; mention this is the OMP counterpart to the opencode provider).
  - **files**: `headroom/providers/omp/__init__.py`
  - **acceptance**:
    - `python -c "from headroom.providers.omp import proxy_base_url, build_launch_env, omp_home_dir, omp_models_yml_path, omp_mcp_config_path, omp_config_paths, snapshot_omp_models_if_unwrapped, strip_omp_headroom_blocks, inject_omp_proxy_config, restore_omp_models_yml"` exits 0.
    - `from headroom.providers.omp import _CONFIG_MARKER_START` succeeds (marker constants are part of the export contract for symmetry with opencode).
    - `__all__` is a `list[str]` containing every exported name.

---

## Wave 2: `OmpRegistrar` MCP registrar

<!--
Wave 2 creates headroom/mcp_registry/omp.py with the OmpRegistrar class. The class follows
OpencodeRegistrar's shape exactly; the only delta is the file format (mcpServers key in .omp/mcp.json
instead of mcp key in opencode.json) and the entry shape ({command, args, env} instead of
{type, command: [...], enabled}). This is scaffolding because ph.1 doesn't call register_server from
the CLI — ph.2 owns the call site. But every method must be implemented so ph.2's tests can hit them.
-->

- [ ] task-2.1: [type:scaffolding] Create `OmpRegistrar` class in `headroom/mcp_registry/omp.py`
  - **description**: Create `headroom/mcp_registry/omp.py` containing the `OmpRegistrar(MCPRegistrar)` class plus its private helpers, modeled directly on `headroom/mcp_registry/opencode.py`. Required structure: (a) module-private `_read_json(path)` / `_write_json(path, data)` helpers (copied shape from opencode registrar — return `{}` on `OSError`/`JSONDecodeError`, mkdir parents on write). (b) `_entry_to_spec(name, entry)` — handle the OMP entry shape `{command: str, args: list[str], env: dict[str, str]}` (different from opencode's `{type, command: [...], enabled}`). (c) `_spec_to_entry(spec)` — inverse: `{command: spec.command, args: list(spec.args), env: dict(spec.env) if spec.env else {}}`. (d) `_specs_equivalent(a, b)` and `_diff_specs(existing, requested)` — copied from opencode registrar verbatim. (e) `OmpRegistrar` class with `name = "omp"`, `display_name = "OMP"`, `__init__(config_path: Path | None = None)` defaulting to `Path.cwd() / ".omp" / "mcp.json"`, `detect()` returning `shutil.which("omp") is not None or (Path.cwd() / ".omp").is_dir()`, `get_server(name)` reading `data["mcpServers"]`, `register_server(spec, force=False)` writing to `data["mcpServers"][spec.name] = {command, args, env}`, `unregister_server(name)` removing the key. Match OpencodeRegistrar's exact `RegisterStatus` semantics (REGISTERED/ALREADY/MISMATCH/FAILED).
  - **files**: `headroom/mcp_registry/omp.py`
  - **acceptance**:
    - `python -c "from headroom.mcp_registry.omp import OmpRegistrar; r = OmpRegistrar(); assert r.name == 'omp' and r.display_name == 'OMP'"` exits 0.
    - `OmpRegistrar(config_path=Path("/tmp/x/.omp/mcp.json"))._config_path == Path("/tmp/x/.omp/mcp.json")`.
    - Round-trip: `register_server(ServerSpec(name="headroom", command="headroom", args=("mcp","serve")))` then `get_server("headroom")` returns an equivalent `ServerSpec` (verified by `_specs_equivalent`).
    - `unregister_server("headroom")` returns `True` after registration, `False` after a second call.
    - `register_server` on a mismatch returns `RegisterResult(status=RegisterStatus.MISMATCH, ...)` without `force=True`, and overwrites with `force=True`.

- [ ] task-2.2: [type:scaffolding] Register `OmpRegistrar` in `headroom/mcp_registry/__init__.py`
  - **description**: Read `headroom/mcp_registry/__init__.py` to see how `OpencodeRegistrar` is exported (likely a `__all__` list + top-level import). Add the parallel import: `from .omp import OmpRegistrar` and append `"OmpRegistrar"` to `__all__`. Do NOT yet add it to any "fleet" list (the install-fleet is ph.2's concern — ph.1 only makes the class discoverable). Verify by `python -c "from headroom.mcp_registry import OmpRegistrar"`.
  - **files**: `headroom/mcp_registry/__init__.py`
  - **acceptance**:
    - `from headroom.mcp_registry import OmpRegistrar` succeeds.
    - `"OmpRegistrar"` appears in `headroom.mcp_registry.__all__`.
    - No other behavior of `headroom/mcp_registry/__init__.py` changes (the file's import order and other exports remain identical — verify by `git diff headroom/mcp_registry/__init__.py` showing only the omp-related additions).
  - **depends_on**: [task-2.1]

---

## Wave 3: `wrap omp` and `unwrap omp` CLI command stubs

<!--
Wave 3 appends two Click command stubs to headroom/cli/wrap.py. Both raise NotImplementedError with
a ph.2 pointer. They must be registered (so `headroom wrap --help` lists them and `headroom wrap omp --help`
works), but calling them must exit non-zero with a clear error. Place them at the end of the existing
wrap.command block to avoid shifting other commands' line numbers.
-->

- [ ] task-3.1: [type:scaffolding] Add `@wrap.command("omp")` stub to `headroom/cli/wrap.py`
  - **description**: Append a new `@wrap.command(context_settings={"ignore_unknown_options": True})` decorator block at the end of the `wrap.command` registrations in `headroom/cli/wrap.py` (after the last `@wrap.command(...)` decorator currently in the file — read `headroom/cli/wrap.py` to find the exact insertion point). Decorators + signature must match the opencode stub style: `--port/-p` (default 8787, `IntRange(1, 65535)`), `--no-mcp`, `--no-proxy`, `--verbose/-v`, `--prepare-only` (hidden), plus `@click.argument("omp_args", nargs=-1, type=click.UNPROCESSED)`. Option set is INTENTIONALLY smaller than `wrap opencode` — no `--no-rtk` (OMP doesn't use a CLI context tool per KD-5 in architecture research), no `--no-serena`, no `--code-graph`, no `--learn`/`--memory`, no `--backend`/`--anyllm-provider`/`--region`. The function body raises `NotImplementedError("`headroom wrap omp` is not yet implemented. Use `headroom wrap` with other agents (opencode, claude, codex) in the meantime. See ph.2 for the full wrap implementation.")`. Docstring: `"""Launch OMP through Headroom proxy. [NOT YET IMPLEMENTED]"""`.
  - **files**: `headroom/cli/wrap.py`
  - **acceptance**:
    - `headroom wrap omp --help` exits 0 and lists `--port/-p`, `--no-mcp`, `--no-proxy`, `--verbose/-v`, and the `omp_args` positional.
    - `headroom wrap omp` exits non-zero with stderr containing `NotImplementedError` and the string `ph.2`.
    - `headroom wrap --help` lists `omp` in the subcommand list.
    - `git diff headroom/cli/wrap.py` shows the new block added at the end; no other commands' line numbers shift.

- [ ] task-3.2: [type:scaffolding] Add `@unwrap.command("omp")` stub to `headroom/cli/wrap.py`
  - **description**: Append a new `@unwrap.command("omp")` decorator block at the end of the `unwrap.command` registrations in `headroom/cli/wrap.py` (after the last `@unwrap.command(...)` decorator currently in the file). Decorators: `--port/-p` (default 8787, `IntRange(1, 65535)`) and `--no-stop-proxy` (is_flag). Function signature `def unwrap_omp(port: int, no_stop_proxy: bool) -> None`. Body raises `NotImplementedError("`headroom unwrap omp` is not yet implemented. See ph.2 for the full unwrap implementation.")`. Docstring: `"""Undo ``headroom wrap omp`` edits. [NOT YET IMPLEMENTED]"""`.
  - **files**: `headroom/cli/wrap.py`
  - **acceptance**:
    - `headroom unwrap omp --help` exits 0 and lists `--port/-p` and `--no-stop-proxy`.
    - `headroom unwrap omp` exits non-zero with stderr containing `NotImplementedError` and the string `ph.2`.
    - `headroom unwrap --help` lists `omp` in the subcommand list.
    - `git diff headroom/cli/wrap.py` shows only the additions; no other commands' line numbers shift.
  - **depends_on**: [task-3.1]

---

## Verification

- [ ] `python -c "from headroom.providers.omp import proxy_base_url, build_launch_env, omp_home_dir, omp_models_yml_path, omp_mcp_config_path, omp_config_paths, snapshot_omp_models_if_unwrapped, strip_omp_headroom_blocks, inject_omp_proxy_config, restore_omp_models_yml, _CONFIG_MARKER_START, _CONFIG_MARKER_END"` exits 0.
- [ ] `python -c "from headroom.mcp_registry import OmpRegistrar"` exits 0.
- [ ] `python -m py_compile headroom/providers/omp/__init__.py headroom/providers/omp/config.py headroom/providers/omp/runtime.py headroom/mcp_registry/omp.py headroom/cli/wrap.py` exits 0 (no syntax errors).
- [ ] `headroom wrap omp --help` exits 0.
- [ ] `headroom unwrap omp --help` exits 0.
- [ ] `headroom wrap omp` exits non-zero; stderr contains `NotImplementedError` and `ph.2`.
- [ ] `headroom unwrap omp` exits non-zero; stderr contains `NotImplementedError` and `ph.2`.
- [ ] `git diff --stat` shows changes only in: `headroom/providers/omp/__init__.py` (new), `headroom/providers/omp/config.py` (new), `headroom/providers/omp/runtime.py` (new), `headroom/mcp_registry/omp.py` (new), `headroom/mcp_registry/__init__.py` (OmpRegistrar export added), `headroom/cli/wrap.py` (two new decorator blocks appended).
- [ ] Each wave's acceptance criteria confirmed (manual `python -c` smoke tests as listed above).
- [ ] New code passes `ruff check` (or whatever the project's linter is — verify by running it; do NOT skip).
- [ ] No existing tests broken: run the project's existing unit test suite; delta must be zero failures.
- [ ] No new type errors: run the project's type checker (`mypy` or equivalent) on the changed files; delta must be zero errors.
- [ ] No imports added from ph.2-only modules: `grep -RIn "ph\.2\|inject_opencode\|build_opencode_config_content" headroom/providers/omp/ headroom/mcp_registry/omp.py` returns empty.