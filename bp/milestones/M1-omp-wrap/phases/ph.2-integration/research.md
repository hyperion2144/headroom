# Phase Research: ph.2-integration

> Implementation path investigation for the full OMP wrap/unwrap workflow.

---

## Research Scope

Wire full `headroom wrap omp` and `headroom unwrap omp`: proxy startup, models.yml backup+inject with upstream lookup, `.omp/mcp.json` MCP registration, `.omp/config.yml` marker injection, `omp` binary launch, and full unwrap restoration with upstream mapping cleanup. Three change commits:

1. **c1-basic-wrap**: Replace `NotImplementedError` stubs with real proxy startup, MCP registration, OMP launch, and unwrap
2. **c2-models-yml-inject**: models.yml backup + baseUrl modification + upstream mapping file + config.yml markers + unwrap restoration
3. **c3-proxy-extensions**: `x-headroom-base-url` support for Anthropic handler + `OmpUpstreamRouterTransform` in proxy pipeline

---

## Recommended Approach

**Recommendation**: Implement in three sequential commits (c1 → c2 → c3) per the change split plan in context.md. Each commit is independently testable and reviewable.

**Rationale**: The split cleanly separates concerns — c1 is pure CLI wiring (no new proxy code), c2 is pure config manipulation (no runtime changes), and c3 is pure proxy pipeline extension (no CLI changes). This minimizes merge conflicts and allows each piece to be verified independently. The existing patterns from `opencode` and `codex` wrap commands provide well-tested templates for every aspect of c1 and c2.

---

## Detailed Implementation Paths

### c1-basic-wrap: Wire `omp()` and `unwrap_omp()` stubs

#### `headroom/cli/wrap.py:omp()` — fill the NotImplementedError

**Pattern**: Follow `opencode()` (line ~5487) and `openclaw()` (line ~5336) — they share the same structure: check binary exists, inject config, build env, launch.

**Step-by-step**:

1. **Binary check** — `shutil.which("omp")`. If not found, raise `click.ClickException` with install instructions (e.g., "Install OMP: https://ohmy.pi"). This is a hard requirement per D3 in context.md.

2. **Config injection** — Call `inject_omp_proxy_config(port)` from `headroom/providers/omp/config.py`. This function already exists (ph.1 output) and handles:
   - Snapshotting models.yml to backup
   - Rewriting provider baseUrl's to `http://127.0.0.1:{port}`
   - Writing Headroom marker block into `.omp/config.yml`

3. **Build launch env** — Call `build_launch_env(port)` from `headroom/providers/omp/runtime.py`. Returns `(env_dict, display_lines)`. Sets `HEADROOM_PROXY_URL`.

4. **MCP registration** — Write Headroom MCP server entry into `.omp/mcp.json`. Follow `_inject_memory_mcp_config()` pattern (line ~2042) but for JSON format instead of TOML. The `.omp/mcp.json` file is a JSON object with an `mcpServers` key. The entry should register the headroom memory MCP server. Use `omp_mcp_config_path()` from config.py to get the path.

5. **Upstream mapping env var** — Set `HEADROOM_OMP_UPSTREAM_MAP` in the launch env (path to `.omp/.headroom-upstreams.json`). This is consumed by the proxy transform (c3).

6. **Launch** — Call `_launch_tool()` with:
   - `binary="omp"`
   - `args=omp_args`
   - `env` from build_launch_env + HEADROOM_OMP_UPSTREAM_MAP
   - `port=port`
   - `no_proxy=no_proxy`
   - `tool_label="OMP"`
   - `env_vars_display` from build_launch_env
   - `agent_type="omp"`

**Key considerations**:
- `--prepare-only` flag: should inject config + write upstream map + print info, but NOT launch the binary. This is used by other tools that want Headroom-configured OMP without wrapping.
- `--no-mcp` flag: skip MCP registration
- `--no-proxy` flag: skip proxy startup (reuse existing)
- The `omp_args` tuple from `nargs=-1` click argument passes through to the subprocess

#### `headroom/cli/wrap.py:unwrap_omp()` — fill the NotImplementedError

**Pattern**: Follow `unwrap_opencode()` (line ~5678) — same backup-restore-cleanup flow.

**Step-by-step**:

1. **Restore models.yml** — Call `restore_omp_models_yml()` from config.py. This returns `(status, path)` where status is `"restored"`, `"cleaned"`, `"removed"`, or `"noop"`. Before overwriting, diff backup vs current file and warn if they differ (per D4).

2. **Remove Headroom MCP from `.omp/mcp.json`** — Read the JSON file, remove the `headroom_memory` entry from `mcpServers`, write back. If `mcpServers` becomes empty, optionally remove the file.

3. **Remove Headroom marker from `.omp/config.yml`** — Call `strip_omp_headroom_blocks()` from config.py on the project config file content. If the file becomes empty after stripping, remove it.

4. **Remove upstream mapping** — Delete `.omp/.headroom-upstreams.json` if it exists.

5. **Stop proxy** — Unless `--no-stop-proxy`, stop the Headroom proxy. The existing cleanup mechanism in `_launch_tool` handles this for the wrap case; for unwrap, the proxy stop logic is already in the `unwrap_opencode()` template (lines ~5724-5748).

**Key considerations**:
- The unwrap should be idempotent — if called twice, the second call should be a no-op
- Warning on backup divergence is important: if the user edited models.yml after wrap, restoring the backup would lose their changes. The diff should be shown but not block the operation.

---

### c2-models-yml-inject: Upstream mapping and config injection

#### `headroom/providers/omp/config.py` — new functions

**`_build_upstream_map(models_yml_data: dict) -> dict[str, str]`**:

Parse the models.yml providers dict. For each provider:
1. Check if it has `_headroom_original_baseUrl` (set during inject)
2. Look at the provider's `models` list
3. For each model, map `model_id → original_baseUrl`
4. Also handle the case where a provider has no explicit models list but has `models: ["*"]` or similar wildcard — in that case, skip (can't map without model IDs)

The `api` field of each provider determines which handler the proxy routes through (openai-completions → OpenAI handler, anthropic-messages → Anthropic handler). This is important for c3.

**`_write_upstream_map(mapping: dict[str, str]) -> Path`**:

Write the mapping dict as JSON to `.omp/.headroom-upstreams.json`. Return the path. The file format per context.md D2:
```json
{
  "deepseek-v4-flash": "https://ark.cn-beijing.volces.com/api/plan/v3",
  "MiniMax-M3": "https://api.minimaxi.com/anthropic",
  "qwen3.7-plus": "https://dashscope.aliyuncs.com/compatible-mode/v1"
}
```

**Integration with `inject_omp_proxy_config`**:

After `_modify_provider_base_urls` runs and the modified YAML is written, call `_build_upstream_map` on the modified data and `_write_upstream_map` to persist it. This ensures the mapping is always written during inject.

**Integration with `restore_omp_models_yml`**:

After restoring models.yml, delete `.omp/.headroom-upstreams.json` if it exists.

---

### c3-proxy-extensions: Anthropic `x-headroom-base-url` + OmpUpstreamRouterTransform

#### Anthropic handler: `_resolve_anthropic_upstream_base`

**Location**: `headroom/proxy/handlers/anthropic.py`

**Pattern**: Mirror `_resolve_openai_upstream_base` from `headroom/proxy/handlers/openai.py:113-123`.

```python
_ANTHROPIC_BASE_URL_HEADER = "x-headroom-base-url"

def _resolve_anthropic_upstream_base(request_headers: dict[str, str]) -> str | None:
    raw_base_url = _header_get(request_headers, _ANTHROPIC_BASE_URL_HEADER)
    if raw_base_url is None:
        return None
    normalized = _normalize_origin(raw_base_url)
    if normalized is None:
        return None
    if urlparse(normalized).scheme not in {"http", "https"}:
        return None
    return normalized
```

**Integration into `handle_anthropic_messages`**:

The method already accepts `upstream_base_url: str | None = None` (line ~446). Currently this is only set by route-level callers. We need to add a code path that reads the header when `upstream_base_url` is None:

```python
if upstream_base_url is None:
    upstream_base_url = _resolve_anthropic_upstream_base(dict(request.headers))
```

This should happen early in the handler, before the URL resolution at line ~2191. The constraint from context.md says this must be behind a new code path, not change existing behavior — so we only read the header when `upstream_base_url` is not already provided by the caller.

The downstream code at line ~2191 already handles `upstream_base_url` correctly:
```python
url = (
    build_copilot_upstream_url(upstream_base_url, request.url.path)
    if upstream_base_url
    else f"{self.ANTHROPIC_API_URL}/v1/messages"
)
```

So the only change needed is the header resolution at the top of the handler.

#### OmpUpstreamRouterTransform

**Location**: `headroom/proxy/transforms/omp_router.py` (new file)

**Pattern**: Follow `ToolResultInterceptorTransform` from `headroom/proxy/interceptors/base.py` for the transform interface, but this transform operates at the HTTP request level (not message level), so it doesn't extend `Transform` from `headroom/transforms/base.py`. Instead, it should be a lightweight class that hooks into the proxy's request pipeline.

**Design per context.md D6**:

```python
class OmpUpstreamRouterTransform:
    """Reads HEADROOM_OMP_UPSTREAM_MAP and injects x-headroom-base-url."""
    
    def __init__(self):
        self._mapping: dict[str, str] = {}
        self._load_mapping()
    
    def _load_mapping(self) -> None:
        mapping_path = os.environ.get("HEADROOM_OMP_UPSTREAM_MAP")
        if mapping_path and Path(mapping_path).exists():
            self._mapping = json.loads(Path(mapping_path).read_text())
    
    async def __call__(self, request: Request, call_next) -> Response:
        if not self._mapping:
            return await call_next(request)
        
        # Read model from request body
        body = await request.json()
        model = body.get("model", "")
        upstream = self._mapping.get(model)
        
        if upstream:
            # Inject x-headroom-base-url header
            request.headers.__dict__["_list"].append(
                ("x-headroom-base-url", upstream)
            )
        
        return await call_next(request)
```

**Integration into proxy pipeline**:

In `headroom/proxy/server.py`, add the transform to both the anthropic and openai pipelines, gated on `HEADROOM_OMP_UPSTREAM_MAP`:

```python
_omp_router: list = []
if os.environ.get("HEADROOM_OMP_UPSTREAM_MAP"):
    from headroom.proxy.transforms.omp_router import OmpUpstreamRouterTransform
    _omp_router = [OmpUpstreamRouterTransform()]

self.anthropic_pipeline = TransformPipeline(
    transforms=[*_intercept_prefix, *_omp_router, cache_aligner, anthropic_router],
    provider=self.anthropic_provider,
)
self.openai_pipeline = TransformPipeline(
    transforms=[*_intercept_prefix, *_omp_router, cache_aligner, openai_router],
    provider=self.openai_provider,
)
```

**Alternative: ASGI middleware approach** — Instead of a custom class, we could use FastAPI middleware. However, the transform pipeline is the established pattern in this codebase and keeps the logic consistent with other request transforms.

**Important**: The `OmpUpstreamRouterTransform` operates at the HTTP request level (reading the body, injecting headers), not at the message level like `Transform` subclasses. It should be placed BEFORE the message-level transforms in the pipeline so the header is available when message processing begins.

---

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|--------|
| **Single commit** for all changes | Simpler coordination, one PR | Harder to review, higher risk of merge conflicts | Rejected |
| **Three sequential commits** (c1→c2→c3) | Each independently testable, clear review boundaries, minimal conflicts | Requires sequential merging | **Recommended** |
| **Transport plugin** for upstream routing | No proxy changes needed | Requires JS/TS code, OMP-side changes, breaks isolation | Rejected (context.md D1) |
| **Single upstream** for all providers | Simplest proxy config | Breaks multi-provider setups | Rejected (context.md D1) |
| **Embedding upstream map in models.yml** | Single file to manage | Dirty — pollutes OMP config with Headroom data | Rejected (context.md D2) |
| **CLI flags for upstream mapping** | Explicit, visible | Complex CLI, doesn't scale to many models | Rejected (context.md D2) |
| **ASGI middleware** for OmpUpstreamRouterTransform | Standard FastAPI pattern | Inconsistent with existing transform pipeline pattern | Rejected |
| **Message-level Transform subclass** for routing | Follows existing Transform API | Wrong abstraction — routing is HTTP-level, not message-level | Rejected |

---

## Known Pitfalls

1. **Request body consumption**: FastAPI/Starlette request bodies can only be read once. The `OmpUpstreamRouterTransform` must either clone the body or use `request.json()` carefully. The `read_request_json_with_bytes` helper from `headroom/proxy/helpers` handles this pattern.

2. **Anthropic handler header injection timing**: The `x-headroom-base-url` header must be injected BEFORE the handler reads it. If the transform runs after the handler has already resolved the upstream URL, the header has no effect. Place `OmpUpstreamRouterTransform` at position 0 in the pipeline.

3. **Model ID matching**: The upstream mapping uses exact model ID matching. OMP may send model IDs with different casing or prefixes than what's in models.yml. Consider case-insensitive matching or prefix matching as a fallback.

4. **`.omp/mcp.json` JSON format**: Unlike OpenCode's TOML config, `.omp/mcp.json` is JSON. Use `json.load`/`json.dump` instead of string manipulation. The file structure is `{"mcpServers": {"server_name": {...}}}`.

5. **Backup divergence warning**: When unwrapping, if the user edited models.yml after wrap, restoring the backup silently loses their changes. The diff warning (D4) is critical. Use `filecmp.cmp()` or a simple content diff.

6. **`--prepare-only` edge case**: When `--prepare-only` is used, config is injected and upstream map is written, but the proxy is NOT started and OMP is NOT launched. The `_launch_tool` function doesn't support this mode directly — need to handle it before calling `_launch_tool`.

7. **Multiple wrap sessions**: If a user runs `headroom wrap omp` twice, the second call should be idempotent — detect existing Headroom markers and skip re-injection, or update in place.

8. **OMP version compatibility**: The `.omp/mcp.json` format may change between OMP versions. The implementation should be tolerant of unknown keys in the JSON file.

---

## TDD Implications

- **c1-basic-wrap**: Hard to unit test because it involves subprocess launch and filesystem side effects. Integration test recommended: run `headroom wrap omp --prepare-only` and verify config files are created correctly. Mock `shutil.which` for the binary check test.
- **c2-models-yml-inject**: `_build_upstream_map` and `_write_upstream_map` are pure functions — straightforward to unit test with fixture YAML files. Test: inject with a known models.yml, verify upstream map JSON is correct, then unwrap and verify restoration.
- **c3-proxy-extensions**: `_resolve_anthropic_upstream_base` is a pure function — unit test with various header inputs (present, absent, invalid URL). `OmpUpstreamRouterTransform` needs an integration test: start proxy with `HEADROOM_OMP_UPSTREAM_MAP` set, send a request with a mapped model, verify `x-headroom-base-url` header is injected. Use the existing test infrastructure in `tests/` for proxy tests.
