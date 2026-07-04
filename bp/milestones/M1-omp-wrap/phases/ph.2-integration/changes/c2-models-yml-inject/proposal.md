# Proposal: c2-models-yml-inject

> Align intent, scope, and approach before implementation.

---

## Intent

Add models.yml provider baseUrl modification to the wrap flow and full restoration to unwrap. Generate upstream mapping file for proxy routing. Feature type.

---

## Scope

### In scope
- Extend `inject_omp_proxy_config()` in config.py to modify each provider's `baseUrl` to proxy address
- Store original baseUrl in `_headroom_original_baseUrl` field per provider
- Build model→upstream mapping from modified providers
- Write `.omp/.headroom-upstreams.json` mapping file
- Write Headroom marker block to `.omp/config.yml`
- Implement `restore_omp_models_yml()`: restore from backup or strip markers
- Unwrap: restore models.yml, remove `.omp/.headroom-upstreams.json`, strip config.yml markers
- Diff backup vs current file before overwriting; warn on divergence

### Out of scope
- Proxy-side routing (c3)
- Tests (ph.3)

---

## Approach

When `inject_omp_proxy_config(port)` is called:
1. Snapshot models.yml (existing)
2. Parse YAML, iterate providers, modify baseUrl to `http://127.0.0.1:{port}`
3. Store original baseUrl in `_headroom_original_baseUrl`
4. Build `{model_id: original_baseUrl}` mapping
5. Write `.omp/.headroom-upstreams.json`
6. Append marker block to `.omp/config.yml`

Unwrap: restore models.yml from backup, delete mapping file, strip config.yml markers.

---

## Must-haves
1. SHALL modify each provider's baseUrl to proxy address
2. SHALL generate `.omp/.headroom-upstreams.json` with model→upstream mapping
3. SHALL restore models.yml from backup on unwrap
4. SHALL warn if backup differs from current file
5. SHALL be idempotent (re-wrap safe)

---

## Non-goals
- No proxy pipeline changes
- No OMP launch changes
