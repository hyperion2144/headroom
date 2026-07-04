# Research Summary: OMP Wrap Integration

> Consolidated research conclusion — synthesizes stack, architecture, and pitfalls analysis.

---

## Recommendation

**Implement `headroom wrap omp` following the OpenCode provider pattern**, with:

- **Module**: `headroom/providers/omp/` (config.py + runtime.py + __init__.py)
- **MCP Registrar**: `headroom/mcp_registry/omp.py` (OmpRegistrar → .omp/mcp.json)
- **Wrap/Unwrap**: CLI commands in `headroom/cli/wrap.py` 
- **Dependencies**: PyYAML (already installed 6.0.3) + stdlib json — no new deps

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| YAML parsing | PyYAML 6.0.3 | Already in env; handles anchors, aliases, multi-doc |
| JSON handling | stdlib json | Matches OpencodeRegistrar pattern |
| Config approach | Backup-first + marker fallback | models.yml: full backup; mcp.json: structured; config.yml: backup + markers |
| MCP registration | OmpRegistrar extends MCPRegistrar ABC | Follows existing pattern (ClaudeRegistrar, OpencodeRegistrar) |
| Provider routing | In-place baseUrl modification in models.yml | Modifies each provider's baseUrl to proxy, preserving apiKey/api/other fields |
| Backup suffix | `.headroom-backup` | Matches opencode convention |
| Config markers | YAML `# --- Headroom ... ---` comments | Matches JSON `// --- Headroom ... ---` pattern from opencode |

## Module Structure

```
headroom/providers/omp/
  __init__.py   — exports
  config.py     — models.yml backup/modify/restore, .omp/mcp.json manipulation
  runtime.py    — proxy_base_url, build_launch_env

headroom/mcp_registry/omp.py — OmpRegistrar (register/unregister headroom MCP)

headroom/cli/wrap.py
  + wrap omp command     — @wrap.command("omp")
  + unwrap omp command   — @unwrap.command("omp")
```

## Risk Mitigation

| Risk | Mitigation | Confidence |
|------|------------|------------|
| models.yml backup corruption | Atomic copy2 + sha256 verification on restore | High |
| YAML format loss (comments) | PyYAML FullLoader preserves structure; `yaml.dump()` may reflow output | Medium — store raw text backup |
| Proxy port conflict | Reuse `--port` option pattern; detect in-use ports | High |
| OMP not installed | `shutil.which("omp")` check before launch | High |
| Unwrap left orphan backup | Always clean up backup files; marker fallback for edge cases | High |
| OMP version drift | Use stable config paths (.omp/mcp.json, ~/.omp/agent/models.yml) | Medium |
| Concurrent wrap from different dirs | Wrap client tracking per existing pattern | High |

## Implementation Plan

1. Create `headroom/providers/omp/config.py` — models.yml backup/inject/restore
2. Create `headroom/providers/omp/runtime.py` — launch env builder
3. Create `headroom/providers/omp/__init__.py` — exports
4. Create `headroom/mcp_registry/omp.py` — OmpRegistrar
5. Add `wrap omp` + `unwrap omp` commands to `headroom/cli/wrap.py`
6. Add tests

## Spec Gaps

| Gap | Impact | Action |
|-----|--------|--------|
| models.yml not at project level — global `~/.omp/agent/models.yml` | Need special backup path | Update spec: models.yml is user-level, not project-level |
| YAML comment markers for config.yml | Unwrap accuracy depends on preserving markers | Accept; marker-backed fallback is sufficient |
| OMP retry config may reference modified providers | Unused retry ref could break on unwrap | Handle in unwrap: restore exact raw text |
