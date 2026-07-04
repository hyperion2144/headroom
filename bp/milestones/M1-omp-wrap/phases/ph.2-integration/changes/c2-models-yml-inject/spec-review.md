# Spec Review: c2-models-yml-inject

> Specification compliance review. Cross-references delta-spec SHALL/MUST constraints against implementation.

---

## Overall: PASS

All 25 SHALL/SHALL_NOT constraints from the delta-spec are satisfied by the implementation. No SPEC_DRIFT or SPEC_MISMATCH annotations found. The global spec's existing requirements remain intact.

---

## Constraint Checklist

| # | Constraint | Location | Status | Evidence |
|---|-----------|----------|--------|----------|
| 1 | SHALL generate `.omp/.headroom-upstreams.json` during `inject_omp_proxy_config` | `config.py:263-264` | PASS | `_build_upstream_map(data)` + `_write_upstream_map(mapping)` called inside `inject_omp_proxy_config` after `_modify_provider_base_urls` |
| 2 | SHALL map every concrete model id to its provider's original upstream `baseUrl` | `config.py:289-332` | PASS | `_build_upstream_map` iterates providers, walks `models` list, maps each model `id` to `_headroom_original_baseUrl` |
| 3 | SHALL write valid JSON with sorted keys | `config.py:344` | PASS | `json.dumps(mapping, indent=2, sort_keys=True) + "\n"` |
| 4 | SHALL skip wildcard model ids (`"*"`) | `config.py:329` | PASS | `if not model_id or model_id == "*": continue` |
| 5 | SHALL skip providers without `_headroom_original_baseUrl` | `config.py:316-317` | PASS | `if not original: continue` |
| 6 | SHALL NOT write mapping file when zero providers modified | `config.py:252` | PASS | `_build_upstream_map` / `_write_upstream_map` called only inside `if modified_count:` block |
| 7 | SHALL preserve pre-wrap upstream `baseUrl` in `_headroom_original_baseUrl` | `config.py:191-200` | PASS | Captures `baseUrl` as `original_url`, stores as `_headroom_original_baseUrl` |
| 8 | SHALL rewrite `baseUrl` to `http://127.0.0.1:{port}` | `config.py:197` | PASS | `provider_config["baseUrl"] = proxy_url` where `proxy_url = f"http://127.0.0.1:{proxy_port}"` |
| 9 | SHALL be idempotent across re-wraps | `config.py:191-195` | PASS | Checks `_headroom_original_baseUrl` first; if present uses it as `original_url` instead of current `baseUrl` |
| 10 | SHALL NOT overwrite `_headroom_original_baseUrl` with proxy URL on re-wrap | `config.py:191-193` | PASS | `existing_original = provider_config.get("_headroom_original_baseUrl")` — if truthy, `original_url = existing_original` |
| 11 | SHALL NOT duplicate or corrupt upstream mapping on re-wrap | `config.py:263-264` | PASS | `_write_upstream_map` overwrites the file each time; mapping is identical since `_headroom_original_baseUrl` is preserved |
| 12 | SHALL update `baseUrl` to new port on re-wrap | `config.py:197` | PASS | `baseUrl` is always set to `proxy_url` regardless of whether it's a re-wrap |
| 13 | SHALL keep `_headroom_original_baseUrl` as true pre-wrap upstream on re-wrap | `config.py:191-193` | PASS | Same idempotency check as #10 |
| 14 | SHALL map each model id to true upstream in mapping file on re-wrap | `config.py:263-264, 289-332` | PASS | `_build_upstream_map` reads `_headroom_original_baseUrl` which is preserved |
| 15 | SHALL warn before overwriting divergent live `models.yml` from backup | `config.py:400-406` | PASS | `filecmp.cmp(config_file, backup_file, shallow=False)` → `click.echo(..., err=True)` on mismatch |
| 16 | SHALL emit warning to stderr naming both files | `config.py:401-404` | PASS | `click.echo(f"Warning: {config_file} differs from ... {backup_file} ...", err=True)` |
| 17 | SHALL proceed with restore after warning (non-blocking) | `config.py:409-414` | PASS | No `raise` in the warning branch; restore proceeds with `shutil.copy2` |
| 18 | SHALL NOT emit divergence warning when files match | `config.py:400` | PASS | `filecmp.cmp` returns `True` when files match → warning branch not entered |
| 19 | SHALL proceed normally when files match | `config.py:409-414` | PASS | Restore proceeds unconditionally after the (optional) warning |
| 20 | SHALL remove `.omp/.headroom-upstreams.json` when unwrapping a modified config | `config.py:435` | PASS | `_remove_upstream_map()` called after any non-noop restore |
| 21 | SHALL leave mapping untouched when unwrap is a no-op | `config.py:427-431` | PASS | Early return `"noop", config_file` before `_remove_upstream_map()` |
| 22 | SHALL delete mapping after restore from backup | `config.py:414-415, 435` | PASS | Status set to `"restored"` → falls through to `_remove_upstream_map()` |
| 23 | SHALL delete mapping after marker strip | `config.py:422-425, 435` | PASS | Status set to `"cleaned"` or `"removed"` → falls through to `_remove_upstream_map()` |
| 24 | SHALL NOT delete mapping on noop restore | `config.py:427-431` | PASS | Early return before `_remove_upstream_map()` |
| 25 | SHALL NOT raise error for absent mapping file | `config.py:356-359` | PASS | `try/except FileNotFoundError: pass` in `_remove_upstream_map()` |

---

## Edge Case Coverage

| Edge Case | Covered? | Evidence |
|-----------|---------|----------|
| Empty/missing `providers` key in models.yml | Yes | `config.py:249-250`: `providers = data.get("providers", {})` then `if isinstance(providers, dict) and providers:` |
| Non-dict provider entry | Yes | `config.py:183-184`: `if not isinstance(provider_config, dict): continue` |
| Provider without `baseUrl` | Yes | `config.py:185-186`: `if "baseUrl" not in provider_config: continue` |
| Provider with `baseUrl` but no `models` list | Partial | Provider is modified (counted) but `_build_upstream_map` skips it at `config.py:320-321`; `_write_upstream_map({})` writes empty `{}` when `modified_count > 0` but no models exist. Spec only guarantees no file when `modified_count == 0`. |
| Model id as bare string vs dict | Yes | `config.py:323-328`: handles both `isinstance(model, dict)` and `isinstance(model, str)` |
| Wildcard model id `"*"` | Yes | `config.py:329`: `if not model_id or model_id == "*": continue` |
| Re-wrap with different port | Yes | `config.py:197`: `baseUrl` always updated to new port; original preserved via idempotency check |
| Missing backup file during restore | Yes | `config.py:416`: `elif config_file.exists():` — marker-strip path |
| Missing live config file during restore | Yes | `config.py:398`: `if config_file.exists():` guard before filecmp |
| `filecmp.cmp` raises OSError | Yes | `config.py:407-408`: `except OSError: pass` |
| `shutil.copy2` raises OSError | Yes | `config.py:412-413`: re-raises with descriptive message |
| Mapping file missing during `_remove_upstream_map` | Yes | `config.py:357-358`: `except FileNotFoundError: pass` |
| Noop restore with pre-existing mapping file | Yes | `config.py:427-431`: early return before `_remove_upstream_map()` |

---

## Findings

**NO_ISSUES_FOUND.** All 25 SHALL/SHALL_NOT constraints from the delta-spec are satisfied. The global spec's existing requirements (backup before modification, baseUrl rewrite, restore from backup, marker strip, noop handling) remain intact and are verified. No SPEC_DRIFT or SPEC_MISMATCH annotations found.

One minor observation (not a finding): when `modified_count > 0` but no provider carries a `models` list, `_write_upstream_map({})` writes an empty `{}` to disk. The spec guarantees no file only when `modified_count == 0`. This behavior is safe — the proxy router sees an empty mapping and routes nothing — but could be tightened if desired.
