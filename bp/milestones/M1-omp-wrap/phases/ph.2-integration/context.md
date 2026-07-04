# Context: ph.2-integration

> Phase implementation decisions for full wrap/unwrap workflow.

---

## Phase Goals

Wire full `headroom wrap omp` and `headroom unwrap omp`: proxy startup, models.yml backup+inject with upstream lookup, `.omp/mcp.json` MCP registration, `.omp/config.yml` marker injection, `omp` binary launch, and full unwrap restoration with upstream mapping cleanup.

---

## Architecture Decisions

### D1: Upstream routing via x-headroom-base-url middleware
- **Decision**: Add an "upstream routing transform" to the Headroom proxy that injects `x-headroom-base-url` header into requests based on a model→upstream mapping file (`.omp/.headroom-upstreams.json`). OpenAI handler already reads this header; Anthropic handler will be extended to also read it.
- **Rationale**: Cleanest integration — no OMP-side HTTP client changes needed. Mapping is generated from models.yml during inject.
- **Alternatives considered**: Transport plugin (requires JS/TS code), single upstream (breaks multi-provider), body-parsing middleware

### D2: Model→upstream mapping in JSON file
- **Decision**: Write `.omp/.headroom-upstreams.json` during inject, pass its path to proxy via `HEADROOM_OMP_UPSTREAM_MAP` env var. Mapping: `{model_id: original_baseUrl}` derived from models.yml providers.
- **Rationale**: Decouples mapping generation (config.py) from consumption (proxy transform). JSON is portable.
- **Alternatives considered**: Embedding in models.yml (dirty), CLI flags (complex)

### D3: OMP not found → error exit
- **Decision**: `shutil.which("omp")` check before launch. If not found, raise ClickException with install instructions. No proxy started, no config modified.
- **Rationale**: Clean fail-fast. User must install OMP first.

### D4: Unwrap safety — backup first, warn on divergence
- **Decision**: unwrap restores models.yml from backup if available. Before overwriting, diff backup vs current file and warn if they differ. If no backup, strip Headroom markers from current file.
- **Rationale**: Balances safety (user may have edited) with reliability (100% restoration possible).

### D5: Anthropic handler x-headroom-base-url extension
- **Decision**: Add `x-headroom-base-url` header reading to the Anthropic handler (mirroring `headroom/proxy/handlers/openai.py:_resolve_openai_upstream_base`). When present, it overrides `ANTHROPIC_API_URL` for that request.
- **Rationale**: Enables per-request upstream routing for Anthropic-format providers (minimax-code-cn with `api: anthropic-messages`).

### D6: Upstream transform as proxy pipeline extension
- **Decision**: Add a lightweight `OmpUpstreamRouterTransform` that reads the mapping file once at startup (cached), then on each request:
  1. Read the `model` field from the request body
  2. Look up the upstream URL in the mapping
  3. If found, inject `x-headroom-base-url` header
- **Rationale**: The proxy already has a transform pipeline (`_intercept_prefix` in `server.py:HeadroomProxy.__init__`). Adding a transform there is minimal code and fully isolated.

---

## Interface Contracts

### `.omp/.headroom-upstreams.json` format
```json
{
  "deepseek-v4-flash": "https://ark.cn-beijing.volces.com/api/plan/v3",
  "MiniMax-M3": "https://api.minimaxi.com/anthropic",
  "qwen3.7-plus": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "Qwen/Qwen3.5-4B": "https://api.siliconflow.cn/v1"
}
```

### New/modified functions

```python
# headroom/providers/omp/config.py
def _build_upstream_map(models_yml_data: dict) -> dict[str, str]:
    """Build model_id → original_baseUrl mapping from parsed models.yml."""

def _write_upstream_map(mapping: dict[str, str]) -> Path:
    """Write mapping to .omp/.headroom-upstreams.json, return path."""

# headroom/proxy/handlers/anthropic.py (modified)
# Add _resolve_anthropic_upstream_base(request_headers) → str | None

# headroom/proxy/server.py (modified)
# Add OmpUpstreamRouterTransform to the proxy pipeline
# Read HEADROOM_OMP_UPSTREAM_MAP env var
```

---

## Implementation Constraints

- Must not break existing wrap commands (claude, opencode, codex, etc.)
- `HEADROOM_OMP_UPSTREAM_MAP` env var is optional — absent = no routing transform
- Upstream transform must be a no-op when mapping file is absent or empty
- Anthropic handler `x-headroom-base-url` change must be behind a new code path, not change existing behavior
- models.yml backup file: `{models.yml}.headroom-backup`

---

## Change Split Plan

1. **c1-basic-wrap**: Wire proxy startup, MCP registration in `.omp/mcp.json`, OMP launch. Fill in `headroom/cli/wrap.py` — replace NotImplementedError with real implementation
2. **c2-models-yml-inject**: models.yml backup + baseUrl modification + upstream mapping file + config.yml markers + unwrap restoration
3. **c3-proxy-extensions**: `x-headroom-base-url` support for Anthropic handler + OmpUpstreamRouterTransform

---

## Non-Goals

- Tests (ph.3-hardening)
- Edge case recovery beyond backup+warning
- OMP version compatibility guarantees
