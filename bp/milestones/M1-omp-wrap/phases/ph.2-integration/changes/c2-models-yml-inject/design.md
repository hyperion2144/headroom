# Design: c2-models-yml-inject

> Change Design — models.yml baseUrl modification, upstream mapping file generation, config.yml markers, and unwrap restoration with divergence warning + mapping cleanup.

---

## Context & Goals

**Background.** Phase ph.1 delivered `headroom/providers/omp/config.py` with the inject/restore skeleton: `inject_omp_proxy_config()` rewrites provider `baseUrl`s and writes a marker block into `.omp/config.yml`; `restore_omp_models_yml()` restores from backup or strips markers. c1 wires `omp()`/`unwrap_omp()` in `wrap.py` to call these. Three gaps remain for the proxy-routing story to work end-to-end:

1. **No upstream mapping.** `inject_omp_proxy_config` rewrites `baseUrl` to the proxy but never emits the `{model_id: original_baseUrl}` map that the c3 `OmpUpstreamRouterTransform` needs to route per-model. The mapping file (`.omp/.headroom-upstreams.json`, context.md D2) is the contract between config.py (producer) and the proxy transform (consumer).
2. **Re-wrap idempotency bug.** `_modify_provider_base_urls` always captures the *current* `baseUrl` as `_headroom_original_baseUrl`. On a second wrap the current `baseUrl` is already the proxy URL, so the true upstream is lost and the mapping file would point every model at the proxy itself. There is a dead `provider_config.get("_original_baseUrl", original_url)` probe line that never assigns — a botched attempt at this fix.
3. **Silent restore + no map cleanup.** `restore_omp_models_yml` overwrites the live `models.yml` from backup without warning when the user edited it post-wrap (context.md D4), and it never deletes `.omp/.headroom-upstreams.json`, leaving a stale mapping on disk after unwrap.

**Goals (≤3).**
1. Generate `.omp/.headroom-upstreams.json` during inject so the c3 proxy router can route per-model.
2. Make inject idempotent across re-wraps — preserve the *true* original upstream, not the proxy URL.
3. Make restore warn on backup divergence and clean up the upstream mapping file.

---

## Technical Approach

### Architecture Diagram

```text
~/.omp/agent/models.yml                       [MODIFIED by inject]
  providers:
    volcengine:
      baseUrl: http://127.0.0.1:{port}         ← rewritten (EXISTING)
      _headroom_original_baseUrl: <real>       ← preserved across re-wraps (FIXED)
      api: openai-completions
      models: [{id: deepseek-v4-flash}, ...]
                  │
                  ▼  _build_upstream_map(data)        [NEW]
.omp/.headroom-upstreams.json                 [NEW — written by inject]
  { "deepseek-v4-flash": "https://ark.cn-beijing.volces.com/api/plan/v3", ... }
                  │
                  ▼  consumed by c3 OmpUpstreamRouterTransform
                     (path passed via HEADROOM_OMP_UPSTREAM_MAP — c1's job)
.omp/config.yml                               [EXISTING — marker block, untouched by c2]
  # --- Headroom proxy config --- ... # --- end Headroom ---

unwrap flow (restore_omp_models_yml):
  ├─ if backup exists:
  │    ├─ filecmp.cmp(current, backup) → click.echo(warn, err=True) on diff   [NEW]
  │    ├─ copy2(backup → models.yml); unlink(backup)                          [EXISTING]
  │    └─ unlink(.omp/.headroom-upstreams.json) if exists                     [NEW]
  ├─ elif markers in current: strip                                           [EXISTING]
  └─ else: noop                                                               [EXISTING]
```

### Core Data Structures

```python
# Path helper — single source of truth for the mapping file location.
omp_upstream_map_path() -> Path   # <cwd>/.omp/.headroom-upstreams.json

# Pure producers.
_build_upstream_map(models_yml_data: dict) -> dict[str, str]
    # {model_id: original_baseUrl} derived from providers that carry
    # _headroom_original_baseUrl and a concrete models list. Wildcard
    # model ids ("*") and providers without an original are skipped.

_write_upstream_map(mapping: dict[str, str]) -> Path
    # JSON-dump (indent=2, sort_keys=True) to omp_upstream_map_path(),
    # creating .omp/ if needed. Returns the path written.

# Mapping file format (context.md D2):
# { "deepseek-v4-flash": "https://ark.cn-beijing.volces.com/api/plan/v3",
#   "MiniMax-M3": "https://api.minimaxi.com/anthropic" }
```

### Data Flow

**`inject_omp_proxy_config(port)`** (extended — steps 1–4,7 existing; 5–6 new):

1. `snapshot_omp_models_if_unwrapped` — backup before first touch *(existing)*.
2. Parse `models.yml` YAML *(existing)*.
3. `_modify_provider_base_urls` — **fixed**: if `_headroom_original_baseUrl` already present, keep it as the true original (re-wrap safe); else capture the current `baseUrl`. Set `baseUrl` to `http://127.0.0.1:{port}`. Remove the dead `_original_baseUrl` probe line.
4. Write modified `models.yml` *(existing)*.
5. `_build_upstream_map(modified_data)` → mapping dict *(new)*.
6. `_write_upstream_map(mapping)` → `.omp/.headroom-upstreams.json` *(new)*.
7. Write marker block into `.omp/config.yml` *(existing, unchanged by c2)*.

**`restore_omp_models_yml()`** (extended):

1. If backup exists: `filecmp.cmp(current, backup, shallow=False)` — on mismatch, `click.echo(warning, err=True)` describing the divergence (non-blocking). Then `copy2(backup → models.yml)`, `unlink(backup)` *(existing copy; warning new)*.
2. Delete `.omp/.headroom-upstreams.json` if it exists *(new)*.
3. Else if markers present in current file: strip *(existing)*, then delete mapping *(new)*.
4. Else: noop *(existing)*.

### Interface Design

```python
# headroom/providers/omp/config.py — additions
def omp_upstream_map_path() -> Path:
    """Return ``<cwd>/.omp/.headroom-upstreams.json`` (project-local mapping)."""

def _build_upstream_map(models_yml_data: dict) -> dict[str, str]:
    """Build ``{model_id: original_baseUrl}`` from parsed models.yml providers.

    Iterates ``providers``; for each provider carrying
    ``_headroom_original_baseUrl`` and a concrete ``models`` list, maps every
    model ``id`` to that original. Wildcard ids (``"*"``) and providers
    without a stored original are skipped.
    """

def _write_upstream_map(mapping: dict[str, str]) -> Path:
    """Write ``mapping`` as JSON to ``.omp/.headroom-upstreams.json``.

    Creates the ``.omp/`` directory if needed. Returns the path written.
    """

# headroom/providers/omp/config.py — modified
def _modify_provider_base_urls(providers, proxy_port: int) -> int:
    """Rewrite ``baseUrl`` to the proxy; preserve true original across re-wraps.

    Idempotent: when ``_headroom_original_baseUrl`` is already set, it is kept
    (so a second wrap does not capture the proxy URL as the original).
    """

def inject_omp_proxy_config(port: int) -> None:
    """Snapshot → rewrite baseUrls → write models.yml → write upstream map
    → write config.yml marker block."""

def restore_omp_models_yml() -> tuple[str, Path]:
    """Restore models.yml (warn on backup divergence) and delete the upstream
    mapping file. Returns ``(status, path)`` as before."""
```

---

## File Manifest

| File Path | Description | Action |
|-----------|-------------|--------|
| `headroom/providers/omp/config.py` | Add `json`, `filecmp`, `click` imports; add `omp_upstream_map_path`, `_build_upstream_map`, `_write_upstream_map`; fix `_modify_provider_base_urls` idempotency (remove dead probe, preserve true original); extend `inject_omp_proxy_config` to emit the mapping; extend `restore_omp_models_yml` with divergence warning + mapping cleanup | Modify |
| `headroom/providers/omp/__init__.py` | Export `omp_upstream_map_path` in the import block and `__all__` | Modify |

---

## Test Strategy

### Unit Tests
- `_build_upstream_map`: provider with `models: [{id: x}]` and `_headroom_original_baseUrl` → `{x: url}`; wildcard `"*"` skipped; provider without `_headroom_original_baseUrl` skipped; non-dict provider skipped; empty/missing `providers` → `{}`.
- `_write_upstream_map`: writes valid sorted JSON to `.omp/.headroom-upstreams.json`, creates `.omp/` when absent, returns the path.
- `_modify_provider_base_urls` idempotency: fresh provider captures real `baseUrl`; pre-wrapped provider (already has `_headroom_original_baseUrl` + proxy `baseUrl`) keeps the true original and only updates the proxy `baseUrl`.
- `inject_omp_proxy_config` (tmp_path + monkeypatched `omp_config_paths`/`Path.cwd`): after inject, `models.yml` has proxy `baseUrl`s + `_headroom_original_baseUrl`, and `.omp/.headroom-upstreams.json` exists with the right mapping.
- `restore_omp_models_yml`: backup divergence → warning to stderr (capsys) and restore still proceeds; mapping file deleted on restore; missing mapping file is a no-op.

### Integration Tests
- Deferred to ph.3-hardening: full `headroom wrap omp --prepare-only` → assert files; `headroom unwrap omp` → assert restoration + mapping removal (subprocess/CLI surface).

### TDD Tasks
- task-c2-1 (upstream mapping core), task-c2-2 (inject integration + idempotency), task-c2-3 (restore divergence warning + cleanup) — all `behavior`, RED→GREEN→REFACTOR.

---

## Alternatives

| Approach | Pros | Cons | Rejection Reason |
|----------|------|------|-----------------|
| Embed upstream map inside `models.yml` | Single file to manage | Pollutes OMP config with Headroom data; OMP may reject unknown keys | context.md D2 — keep mapping in a separate JSON file |
| CLI flags passing the mapping to the proxy | Explicit, visible | Does not scale to many models; recompute on every launch | context.md D2 |
| Single upstream for all providers | Simplest proxy config | Breaks multi-provider setups (volcengine + minimax + siliconflow) | context.md D1 |
| Compute mapping in the proxy at startup from `models.yml` | config.py stays unchanged | Couples proxy to OMP's YAML layout; proxy would need PyYAML + models.yml path | config.py owns models.yml knowledge; decoupling is the stated rationale (D2) |
| Block unwrap on backup divergence | Maximum safety | User cannot unwrap a hand-edited config without manual backup surgery | context.md D4 — warn, do not block |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Re-wrap overwrites true original with proxy URL | High (current bug) | High — every model routes to the proxy recursively | Idempotency check in `_modify_provider_base_urls`: keep existing `_headroom_original_baseUrl` |
| User edits to `models.yml` silently lost on restore | Medium | Medium — lost provider config | Non-blocking divergence warning via `click.echo(..., err=True)` before `copy2` |
| Wildcard models (`"*"`) cannot be mapped | Medium | Low — those models get no per-request routing; proxy falls back | Skipped in `_build_upstream_map`; documented in spec |
| `.omp/config.yml` marker block port goes stale on re-wrap with a new port | Low | Low — marker is informational; actual routing is via `models.yml` `baseUrl` | Out of c2 scope; noted for future hardening |
| PyYAML not installed | Low | Medium — inject raises `RuntimeError`; mapping not written | Existing behavior; proxy router is independently gated on `HEADROOM_OMP_UPSTREAM_MAP`, so absence is a clean no-op |
| `_headroom_original_baseUrl` field leaks into OMP's own YAML parsing | Low | Low — underscore-prefixed; OMP ignores unknown keys | Field name already underscore-prefixed (ph.1 decision); unchanged |
