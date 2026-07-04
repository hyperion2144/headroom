# Proposal: c2-mcp-registrar

> Align intent, scope, and approach before implementation.

---

## Intent

Create the `OmpRegistrar` class for registering/unregistering Headroom MCP servers with OMP, following the existing `headroom/mcp_registry/` pattern used by ClaudeRegistrar and OpencodeRegistrar. This enables `headroom_retrieve` tool access in OMP sessions.

---

## Scope

### In scope

- Create `headroom/mcp_registry/omp.py` with `OmpRegistrar(MCPRegistrar)`
- `OmpRegistrar.detect()` — returns True when `.omp/` directory exists in project root
- `OmpRegistrar.register_server(spec)` — writes headroom MCP entry to `.omp/mcp.json` (creates if missing)
- `OmpRegistrar.unregister_server(name)` — removes headroom MCP entry from `.omp/mcp.json`
- Register `OmpRegistrar` in `headroom/mcp_registry/__init__.py` exports
- Add `OmpRegistrar` to `headroom/mcp_registry/install.py` `get_all_registrars()` list

### Out of scope

- Runtime registration during wrap (ph.2)
- Conflict resolution with existing MCP servers (basic detection only)
- YAML config modification

---

## Approach

Extend `MCPRegistrar` ABC from `headroom/mcp_registry/base.py`, following the exact pattern in `headroom/mcp_registry/opencode.py`. Write to `.omp/mcp.json` as the project-level OMP MCP config. Use `ServerSpec` dataclass and `RegisterResult` return types.

---

## Must-haves

1. SHALL implement `detect()` that returns True when `.omp/` exists
2. SHALL implement `register_server()` that writes to `.omp/mcp.json`
3. SHALL implement `unregister_server()` that removes headroom from `.omp/mcp.json`
4. SHALL use the existing `MCPRegistrar`, `ServerSpec`, `RegisterResult` types
5. SHALL be importable from `headroom.mcp_registry.OmpRegistrar`
6. SHALL be listed in `get_all_registrars()`
7. SHALL handle missing `.omp/mcp.json` gracefully (create it)

---

## Non-goals

- No integration with wrap/unwrap commands (c3)
- No user-level MCP config (`~/.omp/agent/mcp.json`)
