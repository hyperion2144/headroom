# Design: c2-mcp-registrar

## Context & Goals

Create the OmpRegistrar class for OMP MCP server registration following the headroom/mcp_registry/ pattern. Already implemented as `headroom/mcp_registry/omp.py` and wired into `__init__.py` and `install.py`.

## Technical Approach

### Architecture Diagram
```
headroom/mcp_registry/omp.py [NEW]
  └── OmpRegistrar(MCPRegistrar)
        ├── detect() → bool
        ├── register_server(spec) → RegisterResult
        └── unregister_server(name) → bool

headroom/mcp_registry/__init__.py [MODIFIED]
  └── exports OmpRegistrar

headroom/mcp_registry/install.py [MODIFIED]
  └── get_all_registrars() includes OmpRegistrar()
```

### Core Data Structures
Reuses MCPRegistrar, ServerSpec, RegisterResult, RegisterStatus from headroom/mcp_registry/base.py.

## File Manifest
| File | Action |
|------|--------|
| headroom/mcp_registry/omp.py | Create (done) |
| headroom/mcp_registry/__init__.py | Modify (done) |
| headroom/mcp_registry/install.py | Modify (done) |
