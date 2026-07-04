# Proposal: c1-basic-wrap

> Align intent, scope, and approach before implementation.

---

## Intent

Replace the NotImplementedError stubs for `wrap omp` and `unwrap omp` with real implementations: start Headroom proxy, register MCP server in `.omp/mcp.json`, and launch `omp` CLI. Unwrap stops proxy and cleans up MCP registration. Feature type.

---

## Scope

### In scope
- Fill `wrap omp` command: start proxy → register headroom MCP via OmpRegistrar → launch `omp` binary
- Fill `unwrap omp` command: stop proxy → unregister headroom MCP via OmpRegistrar
- Handle `--port`, `--no-mcp`, `--no-proxy`, `--verbose`, `--prepare-only` options
- Handle `omp` not in PATH: error exit with install instructions
- Use `_launch_tool` from existing wrap infrastructure

### Out of scope
- models.yml modification (c2)
- Proxy upstream routing extensions (c3)
- Tests (ph.3)

---

## Approach

Follow the `wrap opencode` pattern exactly: `_ensure_proxy()` → OmpRegistrar.register_server() → `_launch_tool(binary="omp")`. Use `shutil.which("omp")` for binary detection. Unwrap: OmpRegistrar.unregister_server() → proxy cleanup.

---

## Must-haves
1. SHALL start Headroom proxy on the specified port
2. SHALL register headroom MCP server in `.omp/mcp.json`
3. SHALL launch `omp` CLI after proxy is ready
4. SHALL error with clear message when `omp` is not in PATH
5. SHALL stop proxy on unwrap (unless `--no-stop-proxy`)

---

## Non-goals
- No models.yml manipulation
- No proxy pipeline changes
