# Change Summary: c1-basic-wrap

## Intent

Replace NotImplementedError stubs for `wrap omp` and `unwrap omp` with real implementations: proxy startup, MCP registration, OMP launch, and unwrap restoration.

## Output Files

| File | Action |
|------|--------|
| `headroom/cli/wrap.py` | Modify |

## Key Decisions

- Followed the opencode wrap pattern: `_ensure_proxy()` → `OmpRegistrar.register_server()` → `_launch_tool(binary="omp")`
- `shutil.which("omp")` check with clear error message including install URL
- Unwrap restores models.yml, strips config.yml markers, unregisters MCP, stops proxy

## Verification

- `headroom wrap omp --help`: PASS
- `headroom unwrap omp --help`: PASS
- NotImplementedError no longer raised: PASS
- `_OMP_INSTALL_URL` constant defined: PASS
