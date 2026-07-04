# Change Summary: c2-models-yml-inject

## Intent

Extend config.py with upstream mapping file generation, models.yml baseUrl modification with re-wrap idempotency, backup divergence warning, and upstream mapping cleanup on unwrap.

## Output Files

| File | Action |
|------|--------|
| `headroom/providers/omp/config.py` | Modify |
| `headroom/providers/omp/__init__.py` | Modify |

## Key Decisions

- Fixed re-wrap idempotency bug: `_headroom_original_baseUrl` is preserved on re-wrap
- Upstream mapping written to `.omp/.headroom-upstreams.json`
- Backup divergence warning uses `filecmp.cmp` before restore
- `_strip_omp_config_markers` added to config.py for reuse

## Verification

- py_compile: PASS
- All imports: PASS
- 3 commits across 3 waves: PASS
