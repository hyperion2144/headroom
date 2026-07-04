# Design: c3-proxy-extensions

> Add `x-headroom-base-url` header reading to the Anthropic handler and add `OmpUpstreamRouterTransform` to the proxy pipeline for per-request upstream routing.

---

## Context & Goals

The OMP wrap feature (milestone M1-omp-wrap) routes LLM requests from the `omp` CLI through the Headroom proxy. OMP's `models.yml` configures multiple providers (DeepSeek, MiniMax, Qwen, SiliconFlow) with different upstream base URLs. During wrap, all provider `baseUrl` entries are rewritten to `http://127.0.0.1:{port}` so traffic flows through Headroom. The original upstream URLs are preserved in a mapping file (`.omp/.headroom-upstreams.json`), keyed by model ID.

The proxy must route each request to the correct original upstream based on the `model` field in the request body. The OpenAI handler already supports this via the `x-headroom-base-url` request header (read at `openai.py:796`). The Anthropic handler does not — it only accepts `upstream_base_url` as a caller-provided parameter.

**Goals:**
1. Add `x-headroom-base-url` header reading to the Anthropic handler, mirroring the existing OpenAI handler pattern.
2. Create `OmpUpstreamRouterTransform` that reads the model→upstream mapping and injects `x-headroom-base-url` into each request before it reaches the handler.
3. Wire the transform into the proxy pipeline, gated on `HEADROOM_OMP_UPSTREAM_MAP` env var, with no-op behavior when absent.

---

## Technical Approach

### Architecture Diagram

```text
  OMP CLI
    │  POST /v1/messages  (body: {"model": "MiniMax-M3", ...})
    │  baseUrl rewritten → http://127.0.0.1:{port}
    ▼
  Headroom Proxy (FastAPI)
    │
    ├─ [EXISTING] CORSMiddleware
    ├─ [EXISTING] _record_headroom_stack    (HTTP middleware)
    ├─ [EXISTING] _security_gate            (HTTP middleware)
    │
    ├─ [NEW] OmpUpstreamRouterTransform     (HTTP middleware)
    │     │  1. Read HEADROOM_OMP_UPSTREAM_MAP env → mapping file path
    │     │  2. Read request body → extract "model" field
    │     │  3. Look up model in {model_id: upstream_url} mapping
    │     │  4. If found: inject x-headroom-base-url into request scope
    │     │  5. Replay body so handler can re-read it
    │     ▼
    ├─ [MODIFIED] Anthropic handler
    │     │  handle_anthropic_messages()
    │     │  → _resolve_anthropic_upstream_base(request.headers)  [NEW]
    │     │  → if header present & upstream_base_url is None:
    │     │      upstream_base_url = resolved header value
    │     │  → URL built via build_copilot_upstream_url(upstream_base_url, ...)
    │     ▼
    └─ [EXISTING] OpenAI handler
          │  _resolve_openai_upstream() already reads x-headroom-base-url
          ▼
     Correct upstream provider (per-model)
```

### Core Data Structures

```python
# headroom/proxy/transforms/omp_router.py (NEW)

class OmpUpstreamRouterTransform:
    """HTTP middleware: injects x-headroom-base-url from a model→upstream mapping.

    Reads HEADROOM_OMP_UPSTREAM_MAP env var at construction time for the
    mapping file path. The mapping is loaded once (cached) and looked up
    per-request by model ID. When a match is found, the x-headroom-base-url
    header is injected into the request scope before the handler runs.

    No-op when: env var absent, file missing, file empty, or model not in mapping.
    """
    _MAPPING_ENV_VAR: str        # "HEADROOM_OMP_UPSTREAM_MAP"
    _HEADER_NAME: str            # "x-headroom-base-url"
    _mapping: dict[str, str]     # {model_id: upstream_base_url}
```

```python
# headroom/proxy/handlers/anthropic.py (MODIFIED — new module-level function)

_ANTHROPIC_BASE_URL_HEADER: str  # "x-headroom-base-url"

def _resolve_anthropic_upstream_base(request_headers: dict[str, str]) -> str | None:
    """Resolve upstream base URL from x-headroom-base-url header.

    Mirrors _resolve_openai_upstream_base (openai.py:113-123).
    Returns normalized origin URL or None if header absent/invalid.
    """
```

### Data Flow

**Step 1 — Mapping file creation (c2, already designed):**
During `headroom wrap omp`, `config.py` writes `.omp/.headroom-upstreams.json`:
```json
{"MiniMax-M3": "https://api.minimaxi.com/anthropic", "deepseek-v4-flash": "https://ark.cn-beijing.volces.com/api/plan/v3"}
```
The wrap command sets `HEADROOM_OMP_UPSTREAM_MAP=.omp/.headroom-upstreams.json` in the proxy's environment.

**Step 2 — Proxy startup:**
`HeadroomProxy.__init__` checks `os.environ.get("HEADROOM_OMP_UPSTREAM_MAP")`. If set, it constructs `OmpUpstreamRouterTransform()` (which loads the mapping file) and registers it as HTTP middleware via `app.middleware("http")`. If unset, no transform is registered — zero overhead.

**Step 3 — Per-request routing:**
1. OMP sends `POST /v1/messages` with `{"model": "MiniMax-M3", ...}` to the proxy.
2. `OmpUpstreamRouterTransform.__call__` intercepts the request:
   - Reads the request body (JSON), extracts `model` field.
   - Looks up `"MiniMax-M3"` in `_mapping` → `"https://api.minimaxi.com/anthropic"`.
   - Injects `x-headroom-base-url: https://api.minimaxi.com/anthropic` into `request.scope["headers"]`.
   - Replays the body by replacing `request._receive` so the handler can re-read it.
3. Request reaches `handle_anthropic_messages()`.
4. Handler calls `_resolve_anthropic_upstream_base(dict(request.headers))` → returns `"https://api.minimaxi.com/anthropic"`.
5. Since `upstream_base_url` param is `None` (no route-level override), the handler sets `upstream_base_url` to the resolved header value.
6. URL is built: `build_copilot_upstream_url("https://api.minimaxi.com/anthropic", request.url.path)`.
7. Request is forwarded to the correct upstream.

**Step 4 — No-OMP (default) path:**
When `HEADROOM_OMP_UPSTREAM_MAP` is unset, no middleware is registered. The handler's `_resolve_anthropic_upstream_base` returns `None` (no header present), and `upstream_base_url` stays `None` → URL falls back to `self.ANTHROPIC_API_URL`. Behavior is identical to pre-change.

### Interface Design

```python
# headroom/proxy/handlers/anthropic.py — new module-level function

_ANTHROPIC_BASE_URL_HEADER = "x-headroom-base-url"

def _resolve_anthropic_upstream_base(request_headers: dict[str, str]) -> str | None:
    """Resolve the upstream base URL from the x-headroom-base-url header.

    Mirrors _resolve_openai_upstream_base from openai.py. Performs:
    1. Case-insensitive header lookup (via _header_get)
    2. Origin normalization (via _normalize_origin — strips path, validates scheme)
    3. Scheme validation (http/https only)

    Args:
        request_headers: Request headers as a plain dict (case-insensitive lookup).

    Returns:
        Normalized origin URL (e.g. "https://api.minimaxi.com") or None if
        the header is absent, empty, or invalid.
    """
```

```python
# headroom/proxy/handlers/anthropic.py — modified handle_anthropic_messages

async def handle_anthropic_messages(
    self,
    request: Request,
    upstream_base_url: str | None = None,  # ← existing param, unchanged
    provider_name: str = "anthropic",
    model_override: str | None = None,
    force_stream: bool = False,
) -> Response | StreamingResponse:
    # ... existing early setup ...

    # [NEW] Resolve upstream from header when caller didn't provide one.
    # This is a NEW code path — when upstream_base_url is already set by a
    # route-level caller, the header is NOT read (preserves existing behavior).
    if upstream_base_url is None:
        upstream_base_url = _resolve_anthropic_upstream_base(dict(request.headers))

    # ... existing URL resolution at line ~2191 uses upstream_base_url ...
```

```python
# headroom/proxy/transforms/omp_router.py — new module

class OmpUpstreamRouterTransform:
    """HTTP middleware for OMP per-request upstream routing.

    Loaded once at proxy startup when HEADROOM_OMP_UPSTREAM_MAP is set.
    Injects x-headroom-base-url header based on model→upstream mapping.

    Constructor:
        __init__(self, mapping: dict[str, str] | None = None) -> None
            - If mapping is provided (test path), use it directly.
            - If mapping is None, read HEADROOM_OMP_UPSTREAM_MAP env var,
              load JSON from that path. Empty/missing file → empty mapping.

    Callable (ASGI middleware interface):
        async __call__(self, request: Request, call_next) -> Response
            - If _mapping is empty: pass through (no-op).
            - Read request body as JSON, extract "model" field.
            - Look up model in _mapping.
            - If found: inject header into request.scope["headers"], replay body.
            - If not found or body unparseable: pass through unchanged.
    """
```

```python
# headroom/proxy/server.py — modified HeadroomProxy.__init__

# [NEW] OMP upstream router — env-gated, same pattern as _intercept_prefix
_omp_router_enabled = bool(os.environ.get("HEADROOM_OMP_UPSTREAM_MAP"))
if _omp_router_enabled:
    from headroom.proxy.transforms.omp_router import OmpUpstreamRouterTransform
    _omp_router_transform = OmpUpstreamRouterTransform()
else:
    _omp_router_transform = None

# ... later, after app creation, register as HTTP middleware ...
if _omp_router_transform is not None:
    @app.middleware("http")
    async def _omp_upstream_router(request, call_next):
        return await _omp_router_transform(request, call_next)
```

---

## File Manifest

| File Path | Description | Action |
|-----------|-------------|--------|
| `headroom/proxy/handlers/anthropic.py` | Add `_resolve_anthropic_upstream_base()` function and `_ANTHROPIC_BASE_URL_HEADER` constant; modify `handle_anthropic_messages()` to call the resolver when `upstream_base_url` is None | Modify |
| `headroom/proxy/transforms/__init__.py` | Package init for new transforms module | Create |
| `headroom/proxy/transforms/omp_router.py` | `OmpUpstreamRouterTransform` class — HTTP middleware that reads model→upstream mapping and injects `x-headroom-base-url` | Create |
| `headroom/proxy/server.py` | Add env-gated `OmpUpstreamRouterTransform` registration as HTTP middleware in `HeadroomProxy.__init__` (following the `_intercept_prefix` env-gating pattern) | Modify |

---

## Test Strategy

### Unit Tests

- **`_resolve_anthropic_upstream_base`** (pure function):
  - Header present with valid HTTPS URL → returns normalized origin
  - Header present with valid HTTP URL → returns normalized origin
  - Header absent → returns None
  - Header present with invalid scheme (ftp://) → returns None
  - Header present with non-URL value → returns None
  - Header present with URL containing path → returns origin only (path stripped)
  - Case-insensitive header lookup (`X-Headroom-Base-Url` matches `x-headroom-base-url`)

- **`OmpUpstreamRouterTransform`**:
  - Mapping contains model → header injected into request scope
  - Mapping does NOT contain model → no header injected (passthrough)
  - Empty mapping → no-op (passthrough, no body read)
  - Missing mapping file (env var set but file deleted) → empty mapping, no-op
  - Malformed JSON body → no header injected, request passes through
  - Body without "model" field → no header injected, passthrough
  - Body replayed correctly after middleware reads it (handler can re-read body)

### Integration Tests

- Start proxy with `HEADROOM_OMP_UPSTREAM_MAP` set, send Anthropic-format request with a mapped model, verify the request reaches the correct upstream (mock upstream with `wiremock`/`httpx` mock).
- Start proxy WITHOUT `HEADROOM_OMP_UPSTREAM_MAP`, send request, verify behavior is identical to pre-change (upstream = `ANTHROPIC_API_URL`).
- Start proxy with env var set but empty mapping file, send request, verify no-op behavior.

### TDD Tasks

- task-c3-1: `_resolve_anthropic_upstream_base` — RED→GREEN→REFACTOR (pure function, straightforward TDD)
- task-c3-2: `OmpUpstreamRouterTransform` — RED→GREEN→REFACTOR (middleware class with body-reading concern)
- task-c3-3: Server wiring — config task (env-gated registration, no TDD)

---

## Alternatives

| Approach | Pros | Cons | Rejection Reason |
|----------|------|------|-----------------|
| **OmpUpstreamRouterTransform as Transform subclass in TransformPipeline.transforms** (literal research.md proposal) | Reuses existing Transform API; fits `transforms=[*_intercept_prefix, *_omp_router, ...]` pattern | `Transform.apply(messages, tokenizer, **kwargs)` operates on parsed message lists — CANNOT inject HTTP headers. By the time the pipeline runs, the handler has already resolved the upstream URL. Header injection at the message-compression layer is architecturally impossible. | The `Transform` ABC is for message compression, not request routing. The `apply()` signature has no access to request headers or scope. Putting a non-Transform object in `TransformPipeline.transforms` crashes at `transform.should_apply()` / `transform.apply()`. |
| **ASGI middleware via `@app.middleware("http")`** (chosen approach) | Correct abstraction for HTTP-header injection; consistent with existing `_security_gate`, `_record_headroom_stack`, `CORSMiddleware`; can read body and modify `request.scope["headers"]` before handler runs | Must handle body replay (Starlette bodies are single-read) | **Selected** — this is the established pattern in this codebase for HTTP-level request preprocessing. The body-replay concern has a well-known Starlette solution. |
| **Handler reads mapping file directly** (no transform/middleware) | Simplest — no middleware, no body replay; handler already parses body for `model` | Couples handler to mapping file format; duplicates lookup logic in both Anthropic and OpenAI handlers; violates separation of concerns (handler should not know about OMP) | Breaks the decoupling design: the transform owns mapping→header, the handler owns header→upstream. |
| **Message-level Transform that passes upstream via kwargs** | Stays within Transform API | Requires modifying every `pipeline.apply()` call site to pass request context through kwargs; handler must extract upstream from kwargs before URL resolution; invasive and fragile | High blast radius — changes to pipeline call sites at anthropic.py:1177, 1207, 1257, 1301, 3099. Violates "minimal code, fully isolated" goal from context.md D6. |
| **Single upstream for all OMP providers** | Zero proxy code — just set `ANTHROPIC_API_URL` to one upstream | Breaks multi-provider setups (DeepSeek + MiniMax + Qwen simultaneously) | Rejected in context.md D1: "breaks multi-provider". |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Body replay breaks handler's `read_request_json_with_bytes` | Medium | High — handler gets empty/garbled body, request fails | Use established Starlette body-replay pattern: read `await request.body()`, replace `request._receive` with a callable that returns the cached bytes. Verify with integration test that handler successfully re-reads body after middleware. |
| Header injection via `request.scope["headers"]` not visible to `request.headers` | Low | High — handler doesn't see the header, routing fails | Starlette's `Request.headers` reads from `scope["headers"]` at access time. Inject as `(b"x-headroom-base-url", value.encode())` tuple in the scope's headers list. Unit test verifies `request.headers.get("x-headroom-base-url")` returns the value. |
| Performance overhead of body reading on every request | Low | Medium — extra JSON parse per request | Gate behind `HEADROOM_OMP_UPSTREAM_MAP` env var (only active during OMP wrap). When mapping is empty, short-circuit before reading body. Non-OMP requests have zero overhead. |
| Existing Anthropic handler behavior changes for non-OMP requests | Low | High — regression in production | The new code path is strictly conditional: `if upstream_base_url is None: upstream_base_url = _resolve_anthropic_upstream_base(...)`. When no header is present (non-OMP), `_resolve_anthropic_upstream_base` returns None, and `upstream_base_url` stays None → identical to pre-change. Integration test verifies this. |
| Model ID mismatch (OMP sends different casing than models.yml) | Medium | Low — request routes to default upstream instead of mapped one | Exact-match lookup first (simplest, predictable). Case-insensitive matching can be added in ph.3-hardening if needed. Document as known limitation. |
| `_header_get` / `_normalize_origin` import from openai.py (private functions) | Low | Low — import works but couples modules | These are module-level functions in openai.py. Import them directly: `from headroom.proxy.handlers.openai import _header_get, _normalize_origin`. If coupling is a concern in ph.3, extract to `headroom/proxy/handlers/_headers.py` shared utility. |
