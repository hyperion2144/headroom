# Tasks: c3-proxy-extensions

> Break the design into executable tasks grouped by wave. Each task includes description, files, acceptance criteria, optional depends_on and spec_ref. type:behavior tasks include RED test descriptions (GIVEN/WHEN/THEN format).

---

## TDD Type Annotations


| type          | Meaning                                                                 | TDD Protocol                                                          |
| ------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `behavior`    | Business behavior — implement a concrete, observable/assertable feature | **RED→GREEN→REFACTOR** (mandatory: test first → implement → refactor) |
| `config`      | Configuration — env vars, CI/CD, lint, tsconfig, etc.                   | Direct implementation, no TDD                                         |
| `refactor`    | Refactoring — improve internal structure without changing behavior      | Verify tests pass → refactor → verify again                           |
| `docs`        | Documentation — README, API docs, comments                              | Direct implementation, no TDD                                         |
| `scaffolding` | Skeleton code — new module shells, directory structure, templates       | Direct implementation, no TDD                                         |


> **Rule**: If a task's core output is "a behavior" (user-perceptible or test-assertable), use `behavior`. If it's just "file exists" or "config takes effect", use `config`/`scaffolding`.

---

## Wave 1: Anthropic handler x-headroom-base-url support

- [ ] task-c3-1: [type:behavior] Add `_resolve_anthropic_upstream_base` to Anthropic handler
  - **description**: Add a module-level function `_resolve_anthropic_upstream_base(request_headers: dict[str, str]) -> str | None` to `headroom/proxy/handlers/anthropic.py` that reads the `x-headroom-base-url` header and returns a normalized origin URL. This mirrors `_resolve_openai_upstream_base` from `openai.py:113-123`. Use `_header_get` for case-insensitive lookup and `_normalize_origin` for URL normalization — import both from `headroom.proxy.handlers.openai` (or duplicate if import creates circular dependency). Add module-level constant `_ANTHROPIC_BASE_URL_HEADER = "x-headroom-base-url"`. Validate scheme is http/https. Return None when header is absent, empty, or invalid.
  - **files**: headroom/proxy/handlers/anthropic.py
  - **acceptance**: `_resolve_anthropic_upstream_base` returns normalized origin for valid URLs; returns None for absent/invalid headers; case-insensitive header lookup works; matches `_resolve_openai_upstream_base` behavior for identical inputs.
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN a request headers dict with "x-headroom-base-url": "https://api.minimaxi.com/anthropic"
    WHEN _resolve_anthropic_upstream_base(headers) is called
    THEN it returns "https://api.minimaxi.com" (origin only, path stripped)
    
    GIVEN a request headers dict with "X-Headroom-Base-Url": "http://localhost:8080" (different casing)
    WHEN _resolve_anthropic_upstream_base(headers) is called
    THEN it returns "http://localhost:8080"
    
    GIVEN a request headers dict without x-headroom-base-url
    WHEN _resolve_anthropic_upstream_base(headers) is called
    THEN it returns None
    
    GIVEN a request headers dict with "x-headroom-base-url": "ftp://invalid.com"
    WHEN _resolve_anthropic_upstream_base(headers) is called
    THEN it returns None (invalid scheme)
    ```

- [ ] task-c3-2: [type:behavior] Integrate `_resolve_anthropic_upstream_base` into `handle_anthropic_messages`
  - **description**: Modify `handle_anthropic_messages()` in `headroom/proxy/handlers/anthropic.py` (signature at line ~443) to call `_resolve_anthropic_upstream_base(dict(request.headers))` when `upstream_base_url` is None. Place the call early in the handler, before the URL resolution at line ~2191. The existing downstream code at line ~2191 already handles `upstream_base_url` correctly: `url = build_copilot_upstream_url(upstream_base_url, request.url.path) if upstream_base_url else f"{self.ANTHROPIC_API_URL}/v1/messages"`. The new code path MUST only activate when `upstream_base_url` is None (no route-level override) — this preserves existing behavior for non-OMP requests where the header is absent and the resolver returns None.
  - **files**: headroom/proxy/handlers/anthropic.py
  - **acceptance**: When `x-headroom-base-url` header is present and `upstream_base_url` param is None, the request is routed to the header-specified upstream. When the header is absent, behavior is identical to pre-change (falls back to `ANTHROPIC_API_URL`). When `upstream_base_url` is explicitly provided by a route-level caller, the header is NOT read (existing behavior preserved).
  - **depends_on**: [task-c3-1]
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN a request with x-headroom-base-url header set to "https://api.minimaxi.com"
    AND upstream_base_url param is None (no route-level override)
    WHEN handle_anthropic_messages processes the request
    THEN the upstream URL is built from "https://api.minimaxi.com" (not ANTHROPIC_API_URL)
    
    GIVEN a request WITHOUT x-headroom-base-url header
    AND upstream_base_url param is None
    WHEN handle_anthropic_messages processes the request
    THEN the upstream URL falls back to ANTHROPIC_API_URL (unchanged behavior)
    
    GIVEN a request with x-headroom-base-url header set to "https://api.minimaxi.com"
    AND upstream_base_url param is explicitly set to "https://override.example.com"
    WHEN handle_anthropic_messages processes the request
    THEN the upstream URL uses the explicit param "https://override.example.com" (header ignored)
    ```

---

## Wave 2: OmpUpstreamRouterTransform

- [ ] task-c3-3: [type:scaffolding] Create `headroom/proxy/transforms/` package
  - **description**: Create the `headroom/proxy/transforms/` directory with an `__init__.py` file. This package holds proxy-level HTTP transforms (distinct from `headroom/transforms/` which holds message-level Transform ABC, and `headroom/proxy/interceptors/` which holds tool-result interceptors).
  - **files**: headroom/proxy/transforms/**init**.py
  - **acceptance**: `headroom.proxy.transforms` is importable as a Python package.

- [ ] task-c3-4: [type:behavior] Implement `OmpUpstreamRouterTransform` class
  - **description**: Create `headroom/proxy/transforms/omp_router.py` containing the `OmpUpstreamRouterTransform` class. This is an HTTP middleware (NOT a `Transform` subclass — see design.md Alternatives for rationale). The class implements `async __call__(self, request, call_next) -> Response`. Constructor reads `HEADROOM_OMP_UPSTREAM_MAP` env var, loads the JSON mapping file into `self._mapping: dict[str, str]`. Accepts optional `mapping` param for test injection. On each request: (1) if `_mapping` is empty, pass through immediately (no body read); (2) read request body as JSON, extract `model` field; (3) look up model in mapping; (4) if found, inject `x-headroom-base-url` header into `request.scope["headers"]` as `(b"x-headroom-base-url", upstream.encode())` tuple; (5) replay body by replacing `request._receive` with a callable returning the cached bytes so the handler can re-read it; (6) call `await call_next(request)`. Handle malformed JSON body and missing `model` field gracefully (pass through without header injection). Handle missing/empty mapping file at construction time (empty mapping, no crash).
  - **files**: headroom/proxy/transforms/omp_router.py
  - **acceptance**: Transform injects `x-headroom-base-url` when model is in mapping; passes through when model not in mapping; passes through when mapping is empty; passes through when body is malformed JSON; body is replayable after middleware reads it (handler can call `read_request_json_with_bytes` successfully); no-op when `HEADROOM_OMP_UPSTREAM_MAP` env var points to missing file.
  - **depends_on**: [task-c3-3]
  - **spec_ref**: specs/omp/spec.md
  - ***RED test***:
    ```
    GIVEN an OmpUpstreamRouterTransform with mapping {"MiniMax-M3": "https://api.minimaxi.com"}
    WHEN a request with body {"model": "MiniMax-M3", "messages": [...]} passes through
    THEN the request scope contains header (b"x-headroom-base-url", b"https://api.minimaxi.com")
    AND the body is replayable (handler can re-read it via read_request_json_with_bytes)
    
    GIVEN an OmpUpstreamRouterTransform with mapping {"MiniMax-M3": "https://api.minimaxi.com"}
    WHEN a request with body {"model": "unknown-model"} passes through
    THEN no x-headroom-base-url header is injected
    AND the request passes through unchanged
    
    GIVEN an OmpUpstreamRouterTransform with empty mapping {}
    WHEN any request passes through
    THEN no body is read (short-circuit no-op)
    AND the request passes through with zero overhead
    
    GIVEN HEADROOM_OMP_UPSTREAM_MAP env var points to a missing file
    WHEN OmpUpstreamRouterTransform() is constructed
    THEN self._mapping is {} (empty, no crash)
    AND all subsequent requests pass through as no-op
    
    GIVEN an OmpUpstreamRouterTransform with non-empty mapping
    WHEN a request with malformed JSON body (not valid JSON) passes through
    THEN no header is injected and the request passes through (no exception raised)
    ```

---

## Wave 3: Wire transform into proxy pipeline

- [ ] task-c3-5: [type:config] Register `OmpUpstreamRouterTransform` as HTTP middleware in `HeadroomProxy.__init__`
  - **description**: Modify `headroom/proxy/server.py` in `HeadroomProxy.__init__` (near line ~781 where `_intercept_prefix` is defined). Add an env-gated conditional following the same pattern as `_intercept_prefix`: check `os.environ.get("HEADROOM_OMP_UPSTREAM_MAP")`; if set, import `OmpUpstreamRouterTransform` from `headroom.proxy.transforms.omp_router`, instantiate it, and register it as HTTP middleware via `@app.middleware("http")` (same pattern as `_security_gate` at line ~2669 and `_record_headroom_stack` at line ~2525). Place the middleware registration after CORS and security middleware but before the route handlers. If env var is unset, no middleware is registered (zero overhead for non-OMP usage). The transform instance should be stored as `self._omp_router` for potential introspection/metrics.
  - **files**: headroom/proxy/server.py
  - **acceptance**: When `HEADROOM_OMP_UPSTREAM_MAP` is set, the middleware is registered and active. When unset, no middleware is registered and proxy behavior is identical to pre-change. The middleware runs before the Anthropic/OpenAI handlers so the `x-headroom-base-url` header is available when the handler resolves the upstream URL.
  - **depends_on**: [task-c3-4]
  - **spec_ref**: specs/omp/spec.md

---

## Verification

- [ ] Python type check passes (`ruff check` / `mypy` if configured)
- [ ] All new and existing tests pass (`pytest`)
- [ ] Each wave's acceptance criteria confirmed (manual or automated)
- [ ] New code passes lint check (`ruff`)
- [ ] No new type errors or warnings introduced
- [ ] Non-OMP requests (no `HEADROOM_OMP_UPSTREAM_MAP`) behave identically to pre-change

