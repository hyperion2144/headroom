# Delta-Spec: omp

> Change: c3-proxy-extensions | Domain: omp

## ADDED Requirements

### Requirement: Anthropic handler upstream routing via x-headroom-base-url header
The Anthropic handler SHALL resolve the upstream base URL from the `x-headroom-base-url` request header when no explicit `upstream_base_url` parameter is provided by the caller.

#### Scenario: Header present routes to specified upstream
- **GIVEN** a request to the Anthropic `/v1/messages` endpoint with the `x-headroom-base-url` header set to a valid HTTP/HTTPS origin URL
- **AND** the `upstream_base_url` parameter is None (no route-level override)
- **WHEN** `handle_anthropic_messages()` processes the request
- **THEN** the upstream URL SHALL be built from the header value via `build_copilot_upstream_url()`
- **AND** the request SHALL be forwarded to that upstream

#### Scenario: Header absent falls back to default
- **GIVEN** a request to the Anthropic `/v1/messages` endpoint without the `x-headroom-base-url` header
- **AND** the `upstream_base_url` parameter is None
- **WHEN** `handle_anthropic_messages()` processes the request
- **THEN** the upstream URL SHALL fall back to `ANTHROPIC_API_URL`
- **AND** behavior SHALL be identical to pre-change

#### Scenario: Explicit upstream_base_url takes precedence over header
- **GIVEN** a request with the `x-headroom-base-url` header set to "https://header.example.com"
- **AND** the `upstream_base_url` parameter is explicitly set to "https://explicit.example.com"
- **WHEN** `handle_anthropic_messages()` processes the request
- **THEN** the upstream URL SHALL use the explicit parameter value ("https://explicit.example.com")
- **AND** the header SHALL NOT be read (existing route-level behavior preserved)

#### Scenario: Invalid header value is ignored
- **GIVEN** a request with `x-headroom-base-url` set to an invalid URL (non-HTTP scheme, malformed)
- **WHEN** `handle_anthropic_messages()` processes the request
- **THEN** the resolver SHALL return None
- **AND** the upstream URL SHALL fall back to `ANTHROPIC_API_URL`

#### Scenario: Case-insensitive header lookup
- **GIVEN** a request with header key `X-Headroom-Base-Url` (any casing)
- **WHEN** the Anthropic handler resolves the upstream
- **THEN** the header SHALL be matched case-insensitively
- **AND** the value SHALL be used for upstream routing

### Requirement: OmpUpstreamRouterTransform — per-request upstream routing
The system SHALL provide an `OmpUpstreamRouterTransform` that injects the `x-headroom-base-url` header into requests based on a model-to-upstream mapping, enabling per-request upstream routing for OMP-wrapped providers.

#### Scenario: Mapped model gets upstream header injected
- **GIVEN** `OmpUpstreamRouterTransform` is active with mapping `{"MiniMax-M3": "https://api.minimaxi.com"}`
- **WHEN** a request with body `{"model": "MiniMax-M3", ...}` passes through the proxy
- **THEN** the `x-headroom-base-url` header SHALL be injected with value `https://api.minimaxi.com`
- **AND** the request body SHALL remain readable by downstream handlers (body replayed)

#### Scenario: Unmapped model passes through unchanged
- **GIVEN** `OmpUpstreamRouterTransform` is active with mapping `{"MiniMax-M3": "https://api.minimaxi.com"}`
- **WHEN** a request with body `{"model": "unknown-model"}` passes through
- **THEN** no `x-headroom-base-url` header SHALL be injected
- **AND** the request SHALL pass through to the handler unchanged

#### Scenario: Mapping loaded once at startup
- **GIVEN** `HEADROOM_OMP_UPSTREAM_MAP` environment variable points to a valid JSON mapping file
- **WHEN** `OmpUpstreamRouterTransform` is constructed
- **THEN** the mapping SHALL be loaded from the file once and cached in memory
- **AND** subsequent requests SHALL use the cached mapping (no file I/O per request)

#### Scenario: Mapping applied to both Anthropic and OpenAI handlers
- **GIVEN** `OmpUpstreamRouterTransform` is registered as HTTP middleware
- **WHEN** a request arrives at either the Anthropic or OpenAI handler endpoint
- **THEN** the transform SHALL intercept and process the request before it reaches the handler
- **AND** both handlers SHALL see the injected `x-headroom-base-url` header

#### Scenario: Malformed request body passes through safely
- **GIVEN** `OmpUpstreamRouterTransform` is active with a non-empty mapping
- **WHEN** a request with a malformed (non-JSON) body passes through
- **THEN** no header SHALL be injected
- **AND** no exception SHALL be raised
- **AND** the request SHALL pass through to the handler unchanged

### Requirement: OmpUpstreamRouterTransform no-op when mapping absent
The `OmpUpstreamRouterTransform` SHALL be a complete no-op — zero overhead, no request inspection — when the `HEADROOM_OMP_UPSTREAM_MAP` environment variable is absent or the mapping file is missing or empty.

#### Scenario: Env var absent — no middleware registered
- **GIVEN** `HEADROOM_OMP_UPSTREAM_MAP` environment variable is not set
- **WHEN** the Headroom proxy starts
- **THEN** no `OmpUpstreamRouterTransform` middleware SHALL be registered
- **AND** all requests SHALL pass through with zero routing overhead

#### Scenario: Mapping file missing — empty mapping, no crash
- **GIVEN** `HEADROOM_OMP_UPSTREAM_MAP` points to a non-existent file path
- **WHEN** `OmpUpstreamRouterTransform` is constructed
- **THEN** the mapping SHALL be empty (`{}`)
- **AND** no exception SHALL be raised
- **AND** all subsequent requests SHALL pass through as no-op (no body read)

#### Scenario: Empty mapping file — short-circuit passthrough
- **GIVEN** `OmpUpstreamRouterTransform` is active but the mapping is empty `{}`
- **WHEN** any request passes through
- **THEN** the request body SHALL NOT be read (short-circuit before body parse)
- **AND** the request SHALL pass through with zero overhead

### Requirement: Non-OMP request behavior preservation
The proxy SHALL NOT change existing request handling behavior for any request when OMP upstream routing is not active, ensuring zero regression risk for non-OMP usage.

#### Scenario: Non-OMP Anthropic request unchanged
- **GIVEN** the proxy is running without `HEADROOM_OMP_UPSTREAM_MAP` set
- **WHEN** an Anthropic-format request arrives without the `x-headroom-base-url` header
- **THEN** the upstream URL SHALL be `ANTHROPIC_API_URL` (unchanged from pre-change behavior)
- **AND** no new code path SHALL execute

#### Scenario: Non-OMP OpenAI request unchanged
- **GIVEN** the proxy is running without `HEADROOM_OMP_UPSTREAM_MAP` set
- **WHEN** an OpenAI-format request arrives
- **THEN** the existing `_resolve_openai_upstream` behavior SHALL be unchanged
- **AND** no `OmpUpstreamRouterTransform` middleware SHALL intercept the request
