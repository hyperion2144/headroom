# Tech Stack Research: OMP Wrap Integration

> Research output — recommended technology stack with alternatives compared for implementing `headroom wrap omp` and `headroom unwrap omp`.

---

## Recommendation

**Existing Python stdlib + PyYAML + follow existing Headroom provider pattern** — reuse the OpenCode provider architecture with minimal new dependencies. OMP wrap is a configuration-injection problem, not a new runtime. The existing headroom provider scaffolding (Click CLI, MCP registrar pattern, backup/snapshot strategy, environment building) directly maps to OMP's YAML/JSON config surface.

---

## Comparison

### C1: YAML vs JSON — how to handle both formats

OMP uses **both formats across its config surface**:

| File | Location | Format | Purpose |
|------|----------|--------|---------|
| `config.yml` | `~/.omp/agent/` + `.omp/` (project) | YAML | General settings, modelRoles, providers, retry chains |
| `models.yml` | `~/.omp/agent/` | YAML | Provider definitions with API type, models, pricing |
| `mcp.json` | `.omp/` (project) | JSON | MCP server registration |
| `.headroom-backup` | same dir as source | varies | Pre-wrap snapshots |

| Criterion | Option A: PyYAML + stdlib json | Option B: Custom parser | Winner |
|-----------|-------------------------------|------------------------|--------|
| Developer familiarity | High — stdlib json + well-known library | Low — custom error-prone code | Option A |
| Maintenance burden | Zero — PyYAML is unmaintained-but-stable 6.0.3, json is stdlib | High — every format edge case hand-coded | Option A |
| Edge cases covered | YAML anchors, aliases, multi-doc, non-ASCII | Fragile — unlikely to handle YAML quirks | Option A |
| Already in environment | Yes — PyYAML 6.0.3 is installed | Would need to be written | Option A |
| Fits existing pattern | Yes — opencode uses stdlib json | No — departs from convention | Option A |

**Verdict: Option A.** PyYAML is already available, stdlib json for MCP. No new dependency to declare.

---

### C2: Models.yml provider injection — how to route through proxy

Models.yml has two API dialects that must be handled differently:

| Provider type | `api` field | What `baseUrl` points to | How to route |
|--------------|------------|-------------------------|-------------|
| Anthropic Messages | `anthropic-messages` | Anthropic API endpoint | Change `baseUrl` to `http://127.0.0.1:{port}/v1` (proxy handles Anthropic format) |
| OpenAI Completions | `openai-completions` | OpenAI-compatible endpoint | Change `baseUrl` to `http://127.0.0.1:{port}/v1` (proxy handles OpenAI format) |

| Criterion | Option A: Modify `baseUrl` in-place per provider | Option B: Inject a `headroom` provider + keep originals | Winner |
|-----------|-----------------------------------------------|------------------------------------------------------|--------|
| Simplicity | Direct, minimal YAML mutation | Requires understanding OMP's provider resolution order | Option A |
| Reversibility | Backup file restores byte-for-byte | Must remember original values | Option A |
| Compatibility | Works with all provider types uniformly | Would need OMP to support `headroom/` model prefix routing | Option A |
| Risk | None if backup exists | New provider name may not integrate with modelRoles | Option A |

**Verdict: Option A.** Modify each provider's `baseUrl` in-place after creating a full backup. The backup guarantees byte-for-byte recovery on unwrap. The proxy listens on a single port and self-routes to the correct upstream based on the request body format (Anthropic vs OpenAI), so both API types work without per-provider changes.

---

### C3: MCP config format — how to register Headroom MCP

| Criterion | Option A: OmpRegistrar extends MCPRegistrar | Option B: Direct JSON mutation in wrap command | Winner |
|-----------|-------------------------------------------|----------------------------------------------|--------|
| Follows existing pattern | Yes — OpencodeRegistrar, ClaudeRegistrar are precedent | No — diverges from architecture | Option A |
| Reusability | Can be reused by other components | Tied to CLI command | Option A |
| Testability | Clean unit tests on registrar class | Harder to test inline CLI logic | Option A |
| Unwrap symmetry | `unregister_server()` method for clean reversal | Must reimplement removal logic | Option A |

**Verdict: Option A.** Implement `OmpRegistrar` following the `MCPRegistrar` ABC in `headroom/mcp_registry/`. The existing base class provides `register_server()`, `unregister_server()`, `detect()`, `server_exists()`. MCP config lives in `.omp/mcp.json` (project-local).

---

### C4: Config.yml marker injection — inject into project `.omp/config.yml`

| Criterion | Option A: Headroom marker block (like opencode JSON comments) | Option B: Headroom section in YAML (top-level `headroom:` key) | Winner |
|-----------|------------------------------------------------------------|--------------------------------------------------------------|--------|
| YAML-appropriate | YAML `# comment` markers work | Cleaner YAML structure | Option A |
| Idempotent removal | Regex strip of marker-delimited block | Simple dict key removal | Draw |
| Risk of corrupting user data | Regex on multi-line YAML can fail | YAML preserve semantics | Option B |
| Simplicity | Straightforward text manipulation | Must parse, modify, re-serialize | Draw |
| Existing precedent | Opencode uses this pattern | No existing pattern | Option A |

**Verdict: Option A with YAML-aware striping.** Use marker comments (`# --- Headroom proxy config ---` / `# --- end Headroom proxy config ---`) that wrap injected YAML blocks, matching the opencode pattern of `// --- Headroom ... ---`. For removal during unwrap, use line-oriented regex that respects YAML comment syntax (`#` instead of `//`). This keeps the pattern consistent with other providers while using YAML-native comment markers.

---

### C5: Backup strategy for models.yml

| Criterion | Option A: Single backup at `models.yml.headroom-backup` | Option B: Timestamped backups | Winner |
|-----------|--------------------------------------------------------|------------------------------|--------|
| Simplicity | One fixed name like opencode pattern | Multiple files to manage | Option A |
| Reversibility | Byte-for-byte restore guaranteed | Same | Option A |
| Multiple wrap cycles | Only first wrap creates backup; subsequent wraps update in-place | Each wrap leaves orphan | Option A |
| Matching opencode pattern | Identical strategy | Diverges | Option A |

**Verdict: Option A.** Backup lives at `models.yml.headroom-backup` alongside the original, exactly matching the opencode convention (`opencode.json.headroom-backup`). The backup is created once on first wrap and never overwritten, guaranteeing a clean revert path.

---

### C6: Python dependencies

| Dependency | Status | Needed for | Notes |
|-----------|--------|-----------|-------|
| `PyYAML` | Already installed (6.0.3) | Parsing/serializing `config.yml` and `models.yml` | No new dependency needed |
| `json` | stdlib | `.omp/mcp.json` | No new dependency needed |
| `shutil` | stdlib | File backup/restore | No new dependency needed |
| `click` | Already installed | CLI commands | No new dependency needed |
| `pathlib` | stdlib | Path manipulation | No new dependency needed |
| `re` | stdlib | Regex for marker detection/stripping | No new dependency needed |

**No new Python dependencies required.** PyYAML is already available in the environment.

---

## Final Selection

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| YAML parsing | `PyYAML` (stdlib) | 6.0.3 | Already installed, handles all YAML quirks (anchors, aliases, non-ASCII) |
| JSON handling | stdlib `json` | stdlib | No new dep; matches opencode/claude registrars |
| MCP registration | `OmpRegistrar extends MCPRegistrar` | n/a | Follows established `headroom/mcp_registry/` ABC pattern |
| Backup strategy | `.headroom-backup` suffix | n/a | Matches opencode convention; byte-for-byte restore |
| Provider injection | In-place `baseUrl` modification per provider | n/a | Works for both `anthropic-messages` and `openai-completions` API types |
| Config injection | Marker-comment delimited YAML blocks | n/a | Matches opencode marker pattern with YAML `#` comment syntax |
| File locations | Project `.omp/` for `config.yml` + `mcp.json` | n/a | Per spec constraint (not `~/.omp/agent/`) |
| CLI framework | Click subcommands on `wrap` / `unwrap` groups | Already in headroom | Follows existing CLI pattern for headroom wrap {agent} |

## Risks

- **YAML corner cases**: If the user's models.yml uses YAML anchors/references (`&`, `*`, `<<:`), a naive YAML dump after round-trip parsing may expand anchors into duplicate keys, producing a valid but structurally different file. **Mitigation**: For models.yml, prefer text-based injection: locate and replace `baseUrl:` lines within each provider block using targeted regex, rather than parse-modify-dump the entire file. Only the backup + in-place `baseUrl` modification path touches models.yml. Config.yml injection uses block markers (not full YAML rewrite).
- **MCP JSON format evolution**: OMP may change its MCP schema. **Mitigation**: Use the `$schema` field in `.omp/mcp.json` as a version hint; OmpRegistrar writes only the `mcpServers.headroom` key without reformatting the rest of the file.
- **OMP binary path**: OMP may not be in PATH. **Mitigation**: Use `shutil.which("omp")` with a clear error message, matching the opencode pattern.
- **Proxy port conflicts**: Default 8787 may be in use. **Mitigation**: Reuse existing `--port` option pattern from other wrap commands.
