# OMP Provider

The OMP provider module implements `headroom wrap omp` and `headroom unwrap omp` — wrapping Oh My Pi (OMP) through the Headroom proxy for context compression, MCP server registration, and provider routing.

## File Layout

| File | Role |
|------|------|
| `~/.omp/agent/models.yml` | Global OMP provider configuration. Modified by `wrap omp` to route traffic through the Headroom proxy. |
| `<cwd>/.omp/config.yml` | Project-local config. Contains Headroom-managed marker block with proxy settings. |
| `<cwd>/.omp/mcp.json` | Project-local MCP server configuration. Headroom registers its MCP server here. |
| `<cwd>/.omp/.headroom-upstreams.json` | Model-to-upstream URL mapping. Written during wrap, read by the proxy at startup. |

## Backup Convention

Before the first modification, `models.yml` is backed up to `models.yml.headroom-backup` in the same directory. The backup is restored by `unwrap omp`.

## Marker Format

Headroom-managed blocks in `.omp/config.yml` are delimited by comment markers:

```yaml
# --- Headroom proxy config ---
# Provider traffic routed through Headroom proxy on port 8787
# Managed by `headroom wrap omp` / `headroom unwrap omp`
headroom:
  proxy:
    enabled: true
    port: 8787
# --- end Headroom ---
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `PI_CODING_AGENT_DIR` / `OMP_CODING_AGENT_DIR` | Override the OMP agent config directory (default: `~/.omp/agent`). `OMP_CODING_AGENT_DIR` takes precedence. |
| `HEADROOM_OMP_UPSTREAM_MAP` | Path to the JSON mapping file (`{model_id: upstream_baseUrl}`). Set by `headroom wrap omp` when launching the proxy. When unset, no upstream routing middleware is registered. |

## Re-wrap Behavior

On re-wrap, `_headroom_original_baseUrl` is preserved — the original upstream URL captured during the first wrap is kept, not overwritten by the proxy URL from the previous wrap. This ensures unwrap always restores the true original upstream.

## Unwrap Strategies

`unwrap omp` uses the following strategies in order:

1. **Backup restore**: If `models.yml.headroom-backup` exists, restore it and remove the backup file. If the live file differs from the backup, a warning is emitted but the restore still proceeds.
2. **Marker strip**: If no backup exists but Headroom markers are present in `models.yml`, strip the markers. If only marker content remains, the file is removed.
3. **No-op**: If no backup and no markers exist, nothing is done.
