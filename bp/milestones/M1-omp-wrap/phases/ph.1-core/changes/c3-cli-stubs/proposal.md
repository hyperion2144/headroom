# Proposal: c3-cli-stubs

> Align intent, scope, and approach before implementation.

---

## Intent

Register `wrap omp` and `unwrap omp` CLI commands as stubs in `headroom/cli/wrap.py`, following the same Click command pattern as existing wraps (opencode, claude). This establishes the command structure early so future phases can fill in the implementation without touching CLI registration.

---

## Scope

### In scope

- Add `@wrap.command("omp")` to `headroom/cli/wrap.py` with:
  - Standard options: `--port`, `--no-context-tool`, `--no-mcp`, `--no-serena`, `--code-graph`, `--no-proxy`, `--learn`, `--memory`, `--backend`, `--anyllm-provider`, `--region`, `--verbose`, `--prepare-only`
  - `omp_args` variadic argument for passing through to OMP
  - Docstring describing `headroom wrap omp` usage
  - Body: raise `NotImplementedError("Full wrap omp implementation in ph.2-integration")`
- Add `@unwrap.command("omp")` to `headroom/cli/wrap.py` with:
  - Standard options: `--port`, `--no-stop-proxy`
  - Docstring describing unwrap behavior
  - Body: raise `NotImplementedError("Full unwrap omp implementation in ph.2-integration")`
- Import from `headroom/providers/omp/` and `headroom/mcp_registry/omp.py`
- Place both commands in the same alphabetical position as other wraps

### Out of scope

- Actual wrap/unwrap logic — stub only
- Models.yml modification — ph.2
- MCP registration — ph.2
- OMP binary launch — ph.2

---

## Approach

Follow the existing `@wrap.command("opencode")` and `@unwrap.command("opencode")` patterns exactly. Register the commands as Click groups with the same option set. Body raises `NotImplementedError`. Imports are forward-looking (ph.2 will use them) but unused imports are acceptable for stubs.

---

## Must-haves

1. SHALL register `wrap omp` Click command in the `wrap` group
2. SHALL register `unwrap omp` Click command in the `unwrap` group
3. SHALL accept the same standard options as `wrap opencode`
4. SHALL raise `NotImplementedError` when executed
5. SHALL display meaningful help text via `--help`
6. SHALL be placed in the wrap.py file alongside other commands

---

## Non-goals

- No functional wrap/unwrap behavior
- No integration with proxy or OMP
- No test code (tests are ph.3)
