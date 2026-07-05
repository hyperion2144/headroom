# OMP Provider

The OMP provider module implements `headroom wrap omp` and `headroom unwrap omp` — wrapping Oh My Pi (OMP) through the Headroom proxy for context compression and MCP server registration.

## Architecture

Instead of modifying OMP's `models.yml`, Headroom uses an **OMP extension** (`plugins/omp/headroom-proxy.ts`) installed at `~/.omp/agent/extensions/`. The extension intercepts `before_provider_request` events, rewrites the `baseUrl` to the Headroom proxy, and injects the `x-headroom-base-url` header so the proxy can route to the correct upstream provider.

## File Layout

| File | Role |
|------|------|
| `~/.omp/agent/extensions/headroom-proxy.ts` | OMP extension installed by `wrap omp`. Intercepts provider requests and routes them through Headroom. |
| `~/.omp/agent/mcp.json` | Global OMP MCP configuration. Headroom registers its MCP server here. |

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

## Unwrap

`unwrap omp` strips Headroom markers from `.omp/config.yml`, removes the Headroom MCP server, and uninstalls the proxy extension from `~/.omp/agent/extensions/`.
