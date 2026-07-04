# Roadmap: headroom — OMP Wrap Integration

> Planning mode: technical-layer
> Milestones are major delivery checkpoints, not feature buckets. Each milestone represents a complete, demonstrable, shippable state.
> Naming: milestone M<number>-<kebab>, phase ph.<number>-<kebab>

---

## Milestones

### M1-omp-wrap: OMP (Oh My Pi) Wrap Integration
- **Goal**: `headroom wrap omp` and `headroom unwrap omp` commands that start proxy, inject OMP configuration, register MCP server, and launch/restore OMP.
- **Mode**: technical-layer
- **Success Criteria**:
  - `headroom wrap omp` starts proxy, configures `.omp/mcp.json`, injects models.yml routing, marks `.omp/config.yml`, and launches `omp`
  - `headroom unwrap omp` restores all OMP configuration to pre-wrap state
  - Headroom MCP server is registered in `.omp/mcp.json` and retrievable via `headroom_retrieve`
  - All operations are idempotent and fully reversible
  - Existing tests pass; new tests cover wrap/unwrap workflows

#### Phases

| ID | Goal | Depends On | Deliverable |
|----|------|-----------|-------------|
| ph.1-core | OMP provider module + MCP registrar + CLI command skeleton | - | `headroom/providers/omp/` module, `OmpRegistrar`, CLI command stubs |
| ph.2-integration | Full wrap/unwrap workflow — models.yml injection, config markers, backup/restore | ph.1 | Working `wrap omp` and `unwrap omp` commands |
| ph.3-hardening | Tests, error handling, edge cases, cross-version safety | ph.2 | Test suite passing, robust error recovery |

#### ph.1-core
- **Goal**: Create the OMP provider module following the Opencode pattern, with config file helpers, MCP registrar, and CLI command skeleton.
- **Deliverable**: `headroom/providers/omp/config.py` (snapshot/inject/strip), `headroom/providers/omp/runtime.py` (launch env), `headroom/mcp_registry/omp.py` (OmpRegistrar), CLI `wrap omp`/`unwrap omp` command registration (stubs that print "not implemented").
- **Inputs**: `bp/specs/omp/spec.md`, `bp/research/architecture.md`, `headroom/providers/opencode/*` (reference)
- **Outputs**: Provider module, MCP registrar, CLI stubs

#### ph.2-integration
- **Goal**: Wire full wrap/unwrap: proxy startup, models.yml backup+inject, `.omp/mcp.json` MCP registration, `.omp/config.yml` marker injection, `omp` binary launch, and full unwrap restoration.
- **Deliverable**: Working `headroom wrap omp` (proxy → configure → launch) and `headroom unwrap omp` (restore → cleanup).
- **Inputs**: `bp/specs/omp/spec.md`, ph.1 outputs
- **Outputs**: Functional wrap/unwrap commands

#### ph.3-hardening
- **Goal**: Tests, edge case handling (missing files, port conflicts, partial wraps), cross-version compatibility, documentation.
- **Deliverable**: Test suite (`test_wrap_omp.py`, `test_providers_omp_config.py`, `test_mcp_registry_omp.py`), robust error recovery.
- **Inputs**: ph.2 outputs, `bp/specs/omp/spec.md`
- **Outputs**: Tested, hardened integration

---

## Dependency Graph
```text
ph.1-core ──→ ph.2-integration ──→ ph.3-hardening
```
