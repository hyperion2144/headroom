# Proposal: c1-provider-module

> Align intent, scope, and approach before implementation.

---

## Intent

Create the OMP provider module (`headroom/providers/omp/`) following the same structure as `headroom/providers/opencode/`. This provides config file helpers and runtime launch env builders needed by the wrap/unwrap commands. All affected: headroom CLI team. Type: feature.

---

## Scope

### In scope

- Create `headroom/providers/omp/__init__.py` with exports
- Create `headroom/providers/omp/config.py` with:
  - `omp_models_yml_path()` — returns `~/.omp/agent/models.yml`
  - `omp_home_dir()` — returns `~/.omp/agent/`
  - `omp_config_paths()` — returns `(models_yml_path, backup_path)`
  - `snapshot_omp_models_if_unwrapped()` — backup before first injection
  - `strip_omp_headroom_blocks()` — remove Headroom marker blocks
  - `inject_omp_proxy_config()` — modify models.yml baseUrl's + write .omp/mcp.json + mark .omp/config.yml
  - `restore_omp_models_yml()` — restore from backup or strip markers
- Create `headroom/providers/omp/runtime.py` with:
  - `proxy_base_url()` — returns local proxy URL for given port
  - `build_launch_env()` — build env dict for launching OMP

### Out of scope

- Models.yml actual modification at runtime — wire-up in ph.2
- `.omp/mcp.json` actual MCP server registration — handled by c2
- CLI command implementation — handled by c3
- Integration tests — handled in ph.3

---

## Approach

Follow `headroom/providers/opencode/` structure: `config.py` for file manipulation, `runtime.py` for launch env. Use PyYAML 6.0.3 for YAML parsing and stdlib `json` for JSON config. Config markers use `# --- Headroom ... ---` YAML comments matching opencode's `// ---` JSON convention. Backup suffix `.headroom-backup` matches opencode.

---

## Must-haves

1. SHALL create all 3 files in `headroom/providers/omp/`
2. SHALL expose all functions listed in the Interface Contracts section of context.md
3. SHALL NOT import from ph.2-only modules
4. SHALL follow the exact same pattern as `headroom/providers/opencode/`
5. SHALL use PyYAML (no custom YAML parser)
6. SHALL use `.headroom-backup` backup suffix

---

## Non-goals

- No runtime execution of wrap/unwrap flow
- No OMP binary detection or launch
- No integration testing
