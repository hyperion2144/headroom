# Proposal: c3-proxy-extensions

> Align intent, scope, and approach before implementation.

---

## Intent

Add `x-headroom-base-url` header reading to the Anthropic handler (matching existing OpenAI handler) and add OmpUpstreamRouterTransform to the proxy pipeline for per-request upstream routing. Feature type.

---

## Scope

### In scope
- Add `_resolve_anthropic_upstream_base(request_headers)` to Anthropic handler (mirroring `_resolve_openai_upstream_base` in openai.py)
- Modify `handle_anthropic_messages()` to use the resolved upstream when present
- Create `OmpUpstreamRouterTransform` class in `headroom/proxy/transforms/omp_router.py`
- Transform reads `HEADROOM_OMP_UPSTREAM_MAP` env var for mapping file path
- On each request: parse model from body → look up upstream → inject `x-headroom-base-url` header
- Wire transform into proxy pipeline via `_intercept_prefix` in server.py
- Transform is no-op when env var is absent or file missing

### Out of scope
- models.yml modification (c2)
- Tests (ph.3)
- OMP launch changes (c1)

---

## Approach

1. Add `_resolve_anthropic_upstream_base()` to `headroom/proxy/handlers/anthropic.py` that reads `x-headroom-base-url` from request headers
2. Pass resolved upstream to `handle_anthropic_messages()` 
3. Create `OmpUpstreamRouterTransform` that reads mapping file, intercepts requests, injects header
4. Add transform to `_intercept_prefix` in `HeadroomProxy.__init__` when env var is set

---

## Must-haves
1. SHALL add `x-headroom-base-url` reading to Anthropic handler
2. SHALL create OmpUpstreamRouterTransform
3. SHALL wire transform into proxy pipeline
4. SHALL be no-op when `HEADROOM_OMP_UPSTREAM_MAP` is absent
5. SHALL NOT change existing behavior for non-OMP requests

---

## Non-goals
- No OMP-specific code outside proxy
- No models.yml changes
