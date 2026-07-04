# Research Pitfalls: omp-wrap

> Research output — known risks, anti-patterns to avoid, and mitigation strategies for wrapping OMP (Oh My Pi, v16.3.5) through Headroom proxy.

---

## Known Risks

### R-1: models.yml YAML round-trip corruption

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | high |
| **Impact** | high |
| **Risk** | `models.yml` contains deeply nested YAML with inline comments, block scalars, `compat` subtrees, `cost` dicts, `thinking` sub-objects, and model lists. Standard `pyyaml` (`yaml.dump()`) does **not** preserve comments, key ordering, or formatting. Rewriting via dump→load round-trip destroys user annotations and may reorder fields, causing OMP to fail model resolution. The existing Headroom codebase uses JSON throughout — there is no YAML handling precedent. |

**Mitigation A** — surgical text replacement on `baseUrl` lines only (no round-trip):
- Parse `models.yml` line-by-line or with regex targeting `baseUrl:` within provider blocks.
- Replace only the value portion of `baseUrl: <original>` → `baseUrl: http://127.0.0.1:8787/v1`.
- Enclose each modified provider in comment markers (e.g., `# --- Headroom proxy provider ---` / `# --- end Headroom proxy provider ---`) so unwrap can reverse without a backup.
- **Trade-off**: Fragile if YAML uses multi-line or flow-style `baseUrl`, or if providers use aliases/anchors (`&provider` / `*provider`).

**Mitigation B** — `ruamel.yaml` with comment-preserving round-trip:
- Use `ruamel.yaml` (which preserves comments, key ordering, and formatting) for the YAML parse→modify→write loop.
- Set `yaml.indent(mapping=2, sequence=4)` and `yaml.width=4096` to match OMP's default style.
- Wrap in a try/except that falls back to Mitigation A on parse failure.
- **Trade-off**: `ruamel.yaml` is an additional dependency (not yet in project); slower on large files; can still falter on unusual YAML features (tags, complex anchors).

**Recommendation**: **Mitigation A for the initial implementation** (text-level mutation with comment markers), with a planned path to Mitigation B if user reports of comment loss surface. The spec's `models.yml.headroom-backup` backup mechanism provides a safety net for recovery.

### R-2: models.yml provider routing correctness

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | high |
| **Risk** | Not all providers in `models.yml` have a `baseUrl` field (e.g., built-in providers like `opencode-go` may derive `baseUrl` from SDK defaults). Blanket rewriting of every `baseUrl` could silently break providers that don't intend to proxy. OMP uses provider aliasing (`opencode-go/deepseek-v4-flash`) where `opencode-go` is the provider name — if that provider's `baseUrl` is absent, the wrap leaves it unproxied, creating a split-routing scenario where *some* requests go through Headroom and others don't. |

**Mitigation A** — provider-scoped baseUrl injection:
- For each provider entry in `models.yml`, check if `baseUrl` exists. If yes, back it up inline (comment marker) and rewrite it. If no, **skip** that provider and log a warning.
- On unwrap, restore only providers that were marked.
- Provider `opencode-go` is handled specially because it's often the default model role — emit a diagnostic during wrap if the default model routes through an unmodified provider.

**Mitigation B** — wholesale `proxy` wrapper:
- Instead of per-provider `baseUrl` mutation, configure OMP's global proxy settings if OMP supports a `HTTP_PROXY`/`HTTPS_PROXY` or `proxy` config key. This catches **all** outbound traffic without touching individual providers.
- **Trade-off**: Spec explicitly requires `baseUrl`-level injection (FR-4). Global proxy would also proxy non-LLM traffic (plugin downloads, telemetry), and OMP may not have a global proxy setting.

**Recommendation**: **Mitigation A** — per-provider baseUrl rewrite with skip-on-absent. This directly satisfies FR-4 while avoiding silent routing failures. Add a post-wrap diagnostic that lists which providers were modified and which were skipped.

### R-3: models.yml backup safety

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | critical |
| **Risk** | `models.yml.headroom-backup` could be overwritten on a second `wrap` call if the user wraps again without unwrapping first (idempotency violation). If wrap crashes mid-write, the backup could be truncated. On macOS, `.headroom-backup` suffix files may be ignored by Time Machine if the user expects file-level recovery. |

**Mitigation A** — timestamped backup:
- Name backup as `modelsyml.{timestamp}.headroom-backup` (ISO-8601 millisecond). Keep at most 3 backups, rotating oldest.
- On wrap, if a backup already exists (from a prior wrap), treat it as the canonical restore point and do **not** overwrite it. Only overwrite after an explicit `unwrap` clears state.
- Validate backup integrity via `yaml.safe_load()` after write.

**Mitigation B** — idempotent backup:
- Before writing backup, compare current `models.yml` checksum against backed-up checksum. If they match (user hasn't changed files since last wrap), skip backup. If they differ, create a new timestamped backup.
- Store backup manifest listing all backup files and their original paths.

**Recommendation**: **Mitigation A** (timestamped + no-overwrite) for simplicity. It guarantees a clean restore path regardless of how many wraps the user performs. Works within the spec's `models.yml.headroom-backup` naming convention by using a directory or index file.

### R-4: .omp/mcp.json JSON formatting preservation

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | medium |
| **Risk** | OMP's `mcp.json` has a specific structure: `$schema` (top-level string), `disabledServers` (array of strings), `mcpServers` (object). Writing via `json.dump()` with fixed indent could alter the file's existing formatting (e.g., 4-space vs 2-space indent, trailing newline presence). The `$schema` field must be preserved. If the user has a `.omp/mcp.json` with comments (JSONC / JSON with comments) — OMP's schema URL suggests JSON Schema-aware editors — a strict JSON parse would strip them. |

**Mitigation A** — JSON AST manipulation (no full round-trip):
- Parse the JSON with `json.loads()`, then surgically insert the headroom MCP server entry into `data["mcpServers"]`.
- Re-serialize with `json.dumps(data, indent=2, sort_keys=False)` to approximate OMP's style.
- Accept that the shim rewrite loses the original file's indent width; document this in wrap output.

**Mitigation B** — read→modify→write with JSONC awareness:
- Attempt to parse with `json5` or `commentjson` (preserves comments). If not available, fall back to strict JSON.
- Before writing, detect the original file's indentation (count leading spaces on the first object line) and use that for the output.
- Preserve `$schema`, `disabledServers`, and all other top-level keys exactly.

**Recommendation**: **Mitigation A** with indentation detection. The spec mandates JSON format; JSONC/comment support is nice-to-have. Detection of original indent width is a ~5-line heuristic. Key is to avoid `sort_keys=True` which would reorder the existing provider entries.

### R-5: .omp/mcp.json conflict with existing MCP servers

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | low |
| **Impact** | medium |
| **Risk** | The user may already have an MCP server named `headroom` registered (from a prior failed wrap or manual setup). Registering a second one with different `command`/`args` would confuse OMP. OMP's MCP implementation might merge or overwrite duplicate keys, leading to silent configuration drift. |

**Mitigation A** — compare-and-skip on match:
- If `headroom` already exists in `mcpServers`, compare its `command`/`args` with the desired headroom spec.
- If they match → return `RegisterStatus.ALREADY`, no-op.
- If they differ → return `RegisterStatus.MISMATCH` with a diff log, and do **not** overwrite. The user must resolve manually.

**Mitigation B** — force-overwrite with backup:
- If `headroom` exists with a different config, back up the current conflicting entry (save to `.omp/mcp.json.headroom-backup`) before overwriting.
- During unwrap, restore from the per-entry backup.

**Recommendation**: **Mitigation A** (compare-and-skip). This follows the existing `OpencodeRegistrar` pattern where `_specs_equivalent()` is checked before any write. The user can always `unwrap` + `wrap` to force a clean state.

### R-6: .omp/config.yml YAML merge precedence

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | high |
| **Risk** | `config.yml` is OMP's main configuration file with ~60+ keys across deeply nested sections (`mcp:`, `bash:`, `async:`, `skills:`, `lsp:`, `retry:`, `snapcompact:`, `display:`, `mnemopi:`, etc.). Injecting a `headroom:` top-level key is generally safe (YAML ignores unknown keys), but if OMP's parser does strict validation, an unknown key could cause startup failures. Rewriting the entire file with `yaml.dump()` could reorder sections, changing OMP's behavior if section ordering matters. |

**Mitigation A** — append-only marker injection:
- Do **not** round-trip the entire file. Instead, append a YAML comment block at the end:
  ```yaml
  # --- Headroom managed ---
  headroom:
    proxy_url: http://127.0.0.1:8787
    mcp_enabled: true
  # --- end Headroom managed ---
  ```
- On unwrap, strip lines between the marker comments.
- **Trade-off**: If OMP re-reads the file and strips unknown keys, the marker is inert but harmless. The configuration effect is achieved via models.yml and mcp.json, not config.yml.

**Mitigation B** — structured injection with ruamel.yaml:
- Parse with `ruamel.yaml`, insert the `headroom:` key with proper indentation, write back.
- Verify that OMP ignores unknown keys by testing against OMP 16.3.5 startup.
- Lock to a specific OMP version in docs for compatibility.

**Recommendation**: **Mitigation A** (append marker only). The spec (FR-5) says config should "contain Headroom-related configuration" — a comment section satisfies this without risk of corrupting the main config. The actual proxy routing happens through models.yml and mcp.json. If OMP's parser is strict, the config.yml injection becomes a no-op advisory marker, which is fine.

### R-7: OMP binary PATH resolution

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | high |
| **Risk** | `omp` binary is installed via `bun` at `~/.bun/bin/omp`. This path may not be in the system `PATH` when Headroom is launched (e.g., launched from a GUI app, Docker, or systemd service that doesn't source `.bashrc`/`.zshrc`). `shutil.which("omp")` could return `None`, causing a confusing "command not found" error. |

**Mitigation A** — explicit PATH detection:
- Run `shutil.which("omp")`. If `None`, probe common locations: `~/.bun/bin/omp`, `~/.npm-global/bin/omp`, `/usr/local/bin/omp`, `/opt/homebrew/bin/omp`.
- Emit a clear error message listing the paths probed and suggesting `npm install -g oh-my-pi` or pointing to the OMP install docs.

**Mitigation B** — user-configurable binary path:
- Accept `--omp-bin` flag or `HEADROOM_OMP_BIN` env var to override the binary path.
- If not set, fall back to Mitigation A's discovery logic.
- Store the resolved path in the wrap manifest for use during potential relaunch/reconnect scenarios.

**Recommendation**: **Mitigation B** (configurable + auto-detect). Add `HEADROOM_OMP_BIN` env var support and probe `~/.bun/bin/omp` as the primary fallback. The auto-detection handles 95% of cases, and the override handles edge cases (Nix, asdf, custom install dirs).

### R-8: Proxy readiness race condition

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | high |
| **Risk** | The `headroom wrap omp` workflow: (1) start Headroom proxy, (2) configure OMP, (3) launch `omp`. If OMP launches before the proxy is fully ready (TCP listener not yet bound, TLS cert not generated), OMP's first LLM request will fail with a connection refused error. OMP may cache this failure or immediately switch to a fallback model, never retrying through the proxy. |

**Mitigation A** — connection readiness poll:
- After starting the proxy, poll `http://127.0.0.1:{port}/health` (or a minimal TCP connect to `127.0.0.1:{port}`) with a 30-second timeout, 100ms interval.
- Only launch `omp` after the health check succeeds.
- Reuse Headroom's existing `wait_ready()` in `headroom/install/runtime.py`.

**Mitigation B** — proxy-first + delayed launch:
- Start proxy in background, configure OMP, then display a spinner: "Waiting for proxy ready..."
- Use `headroom install agent wait-ready` if available, or reimplement a lightweight version.
- Launch OMP with a `--no-startup-checks` flag if OMP supports it, so the UI appears immediately but first API call waits for proxy.

**Recommendation**: **Mitigation A** (health check poll). `wait_ready()` already exists in `headroom/install/runtime.py` and follows this exact pattern. Reuse it with a 30s timeout. In the unlikely event of timeout, abort the wrap and roll back configuration changes.

### R-9: Signal handling and process lifecycle

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | medium |
| **Risk** | `omp` runs as an interactive TUI. When the user presses Ctrl+C to exit OMP, the signal may propagate to the Headroom proxy (parent process), shutting it down too. Conversely, if `headroom wrap omp` launches OMP as a subprocess and then Headroom proxy is stopped (crash, OOM kill), OMP is left proxying to a dead endpoint, resulting in silent failures. |

**Mitigation A** — OMP as independent child process:
- Launch OMP via `subprocess.Popen` with `start_new_session=True` so it gets its own process group. Ctrl+C on OMP does not propagate to the parent.
- Trap SIGTERM/SIGINT in the wrapper script to gracefully unwrap before exit.
- Document that users should `headroom unwrap omp` if they manually kill the proxy.

**Mitigation B** — watchdog process:
- Run a watchdog thread that monitors the proxy health. If the proxy dies, notify the user (via OMP terminal output, desktop notification, or log) and offer to unwrap.
- Periodically (every 30s) check proxy liveness. If lost for 3 consecutive checks, auto-initiate unwrap.

**Recommendation**: **Mitigation A** (separate process group) + a health check notification when `omp` exits. Avoid auto-unwrap — that would surprise the user who might want to restart the proxy manually. The key safety property is: killing OMP does not kill the proxy, and vice versa.

### R-10: Unwrap full state restoration

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | critical |
| **Risk** | If the user modifies `models.yml` between wrap and unwrap, restoring from `models.yml.headroom-backup` loses those changes. If the backup file was manually deleted or corrupted, unwrap is left with only marker-based partial recovery. If OMP was upgraded between wrap and unwrap, restored config may be incompatible with the new version. |

**Mitigation A** — diff-aware restore:
- Before restoring from backup, compute a diff between the current `models.yml` and the backup.
- If the only differences are `baseUrl` values (expected from wrap), safely restore.
- If there are **other** differences (user added/removed providers or models), abort with a warning and save the current file as `models.yml.user-modified` before restoring from backup.
- Ask the user to manually merge before completion.

**Mitigation B** — user notification always:
- Always show a diff of changes made during unwrap. If the backup is missing, notify the user and offer the marker-based clean path.
- On missing backup + no markers, emit a clear "nothing to do" message per spec.

**Recommendation**: **Mitigation A** (diff-aware restore). This protects user changes while still providing a clean restore path for the common case. The spec requires the `unwrap` scenario where no backup exists but Headroom markers are present — the diff check naturally handles this fallback.

### R-11: Partial wrap recovery

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | low |
| **Impact** | critical |
| **Risk** | If `headroom wrap omp` crashes or is killed after modifying one file but before modifying another (e.g., models.yml was modified but mcp.json was not), the system is in an inconsistent state. A subsequent `wrap` may see partially modified files and behave unpredictably. A subsequent `unwrap` may find backups for some files but not others. |

**Mitigation A** — transactional wrap with rollback:
- Maintain an in-memory change log during wrap. If any step fails:
  1. Restore any files already modified (from backup).
  2. Remove any backups that were created.
  3. Print the recovery actions taken.
- Write a `.omp/.headroom-wrap-state` file at the start of wrap, delete it on successful wrap completion. If it exists on next wrap/unwrap, assume partial state and clean up.

**Mitigation B** — check-and-skip idempotent steps:
- Before each modification, check if it's already been done (e.g., does `headroom` MCP server already exist? does `baseUrl` already point to proxy? does `headroom:` marker exist in config?).
- If a step is already applied, skip it. This makes a crash mid-wrap benign: the next `wrap` picks up where it left off.
- For unwrap, same approach: check for backup files, check markers, clean up whatever exists.

**Recommendation**: **Mitigation B** (idempotent check-and-skip). This aligns with NFR-2 (idempotency) and is simpler than full transaction rollback. Each mutation step is a no-op if its effect is already observed. The `.omp/.headroom-wrap-state` manifest file (Mitigation A) is still useful as a debugging aid.

### R-12: Cross-version OMP compatibility

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | medium |
| **Impact** | medium |
| **Risk** | OMP is actively developed (v16.3.5 as of research). Future versions may change:
- `models.yml` provider schema (new required fields, renamed fields)
- `mcp.json` format (schema URL may change, `disabledServers` may be removed)
- `config.yml` structure (top-level key renames)
- `omp` binary CLI flags or startup behavior
- Default install path (bun → npm → custom)

**Mitigation A** — version pinning with compat table:
- Detect OMP version (`omp --version`) and maintain a compatibility table inside `OmpRegistrar`:
  ```python
  OMP_COMPAT = {
      (16, 3): { "models_yml_format": "v1", "mcp_json_has_schema": True },
      (16, 4): { "models_yml_format": "v1", "mcp_json_has_schema": True },
  }
  ```
- If the detected version is outside the known range, emit a warning but proceed with best-effort (v1 format).

**Mitigation B** — defensive parsing:
- When reading `models.yml`, use `dict.get("baseUrl")` with fallback rather than assuming the key exists.
- When writing `mcp.json`, only add/remove the `mcpServers` entry; preserve the `$schema` key if present.
- When checking for wrap markers, use loose matching (substring check) rather than exact line matching.
- Avoid depending on undocumented OMP behavior (e.g., config key ordering, specific error messages).

**Recommendation**: **Both A and B**. Version detection with a compat table gives early warning of breaking changes. Defensive parsing ensures graceful degradation across versions. Decouple the parts — compat table can start empty and grow as versions are tested.

### R-13: No existing YAML dependency in project

| Dimension | Detail |
|-----------|--------|
| **Likelihood** | certain |
| **Impact** | medium |
| **Risk** | The Headroom codebase currently has **zero** YAML dependencies. `headroom/fsutil.py` handles UTF-8 text but provides no YAML-specific tooling. Adding `pyyaml` or `ruamel.yaml` introduces a new dependency with potential version conflicts, security surface, and CI pipeline changes. `pip install` may fail in restricted environments. |

**Mitigation A** — use `pyyaml` (stdlib-adjacent):
- Add `pyyaml>=6.0` to `pyproject.toml`. It's widely installed, well-tested, and available on all platforms.
- Accept that comments and formatting are lost on round-trip.
- Use text-level mutation (Mitigation A from R-1) to avoid round-trips where comments matter.

**Mitigation B** — no new dependency, pure-text processing:
- Use regex/line-based processing for YAML. Only insert/remove specific lines (`baseUrl:`) and marker comments.
- Validate YAML structural assumptions with a lightweight `yaml.safe_load()` that's vendored or imported only if available.
- Document that large YAML changes (e.g., adding a provider) require manual wrap.

**Recommendation**: **Mitigation B** (text-based first, add `pyyaml` only if needed). The OMP wrap only needs to:
1. Change `baseUrl` values (text replacement on matching lines)
2. Append comment markers (text append)
3. Add MCP entry (JSON, already handled)
No full YAML round-trip is needed if we use comment markers and text-level surgery. This dodges the dependency problem entirely.

---

## Anti-Patterns to Avoid

- **Full-file YAML round-trip on models.yml**: Loading and re-dumping with `yaml.dump()` destroys user comments, key ordering, and formatting. OMP users curate their models.yml carefully — losing formatting is a support nightmare. Use text-level `baseUrl` mutation instead.

- **Silently overwriting existing `headroom` MCP server**: If the user already has a `headroom` MCP entry with a different configuration, blindly overwriting it breaks their setup. Follow the spec-mismatch pattern from existing registrars.

- **Assuming `omp` is on PATH**: `omp` is installed via `bun install -g oh-my-pi`, which puts it in `~/.bun/bin/omp`. This is rarely in the default system PATH. Always probe common locations explicitly.

- **Launching OMP before proxy is ready**: OMP starts processing immediately. A brief proxy unavailability causes visible errors. The user doesn't distinguish "proxy not ready" from "wrap is broken."

- **Overwriting backup on re-wrap**: If the user runs `wrap` twice, the second call must not destroy the first backup. Use timestamped backups or idempotent skip.

- **Restoring backup blindly on unwrap**: If the user added a new provider between wrap and unwrap, restoring the backup silently deletes it. Always diff before restore.

- **Touching `~/.omp/agent/config.yml` with full-file rewrite**: The config has ~60+ keys with deep nesting. A rewrite likely reorders sections. Append comment-marked blocks instead.

- **Assuming `.omp/` is at project root**: The spec says "project-level config" but some users may symlink `.omp/` or use a non-standard OMP layout. Use `shutil.which("omp")` to locate the OMP home, then `.omp/` relative to the project directory.

---

## Edge Cases

| Edge Case | Handling Strategy |
|-----------|------------------|
| `.omp/` directory does not exist | Create `.omp/` with `mkdir -p` during wrap. Skip config.yml injection. |
| `models.yml` is empty or malformed | Take backup if possible; if YAML parse fails, abort wrap with clear error. |
| Multiple provider entries with same `baseUrl` | Deduplicate by provider name key before modification. |
| `models.yml.headroom-backup` is from a different machine/user | Include hostname + user in backup filename or metadata. |
| OMP is not installed at all | Detect via `shutil.which("omp")`. If absent, print install instructions and abort. |
| Proxy port 8787 is already in use | Detect port conflict before starting proxy. Offer `--port` override or abort. |
| `.omp/mcp.json` is read-only (permission issue) | Wrap with `PermissionError` handling; print the file path and expected mode. |
| User has `.omp/config.yml` in `/dev` or special FS | Bail on write errors; partial wrap recovery (see R-11). |
| Unicode characters in models.yml (Chinese provider names) | `headroom/fsutil.py` uses UTF-8 read/write — correctly handled. |
| Line endings (`\r\n` vs `\n`) | `fsutil.write_text` disables `\n`→`\r\n` translation. On read, `fsutil.read_text` normalizes to `\n`. |
| Concurrent wrap/unwrap from multiple terminals | Use file locking (`.omp/.headroom.lock`) to serialize access. |
| OMP launched but never starts (hangs on TUI init) | Set a 30s timeout on OMP startup. If it exits early or hangs, log the stdout/stderr and offer to unwrap. |

---

## Dependencies at Risk

| Dependency | Version | Status | Concern |
|-----------|---------|--------|---------|
| `omp` binary | 16.3.5 | active | Active development. Version schema may change. See R-12. |
| `pyyaml` / `ruamel.yaml` | N/A | not yet added | No YAML dependency exists in Headroom. Text-level mutation avoids adding one in the initial implementation. |
| `~/.omp/agent/mcp.json` | N/A | active | JSON format with `$schema` field — fragile to formatting changes. |
| `~/.omp/agent/models.yml` | N/A | active | Deeply nested YAML with user comments — most fragile file in the wrap chain. |
| `~/.omp/agent/config.yml` | N/A | active | Wide flat YAML with 60+ settings — avoid round-trip, use marker append. |
| Headroom proxy (self) | current | active | Must be running and healthy before OMP launch to avoid startup failures. |
| `bun` runtime (OMP installs via) | latest | active | OMP binary path depends on bun's global install directory. |

---

## SPEC_GAP: Spec Gaps Identified During Research

The following gaps in `bp/specs/omp/spec.md` were surfaced during the risks analysis. Plan phase should resolve these before implementation.

| # | Gap | Impact | Suggested Resolution |
|----|------|--------|---------------------|
| SG-1 | **Providers without `baseUrl`**: Spec FR-4 says "modify all providers' `baseUrl`" but doesn't address providers that lack a `baseUrl` field entirely (e.g., `opencode-go` built-in provider). | Without handling, those providers bypass the proxy silently. | Clarify: skip providers without `baseUrl`, emit a warning for each. Consider whether `opencode-go` should be an explicit goal to route. |
| SG-2 | **mcp.json `$schema` preservation**: Spec doesn't mention whether the `$schema` top-level field in `.omp/mcp.json` must be preserved on write. | Dropping it could break OMP's JSON Schema validation in editors. | Add requirement: preserve `$schema` and `disabledServers` fields when rewriting `mcp.json`. |
| SG-3 | **Mid-wrap crash recovery**: Spec says "repeat wrap is safe" (NFR-2) but doesn't define recovery contract when wrap crashes after writing only some files (e.g., models.yml done, mcp.json pending). | Inconsistent state on crash; `unwrap` may find backups for file A but not file B. | Define a wrap manifest (`.omp/.headroom.json`) tracking which files were modified, with `completed` flag. On next wrap/unwrap, detect partial state and either roll back or complete. |
| SG-4 | **config.yml missing**: Spec FR-5 assumes `.omp/config.yml` exists but doesn't specify behavior when it doesn't (fresh OMP install). | Wrap may error out on a missing file that's optional. | Clarify: if `.omp/config.yml` doesn't exist, skip injection (or create minimal file with only Headroom markers). |
| SG-5 | **PATH resolution**: Spec says "OMP binary named `omp`" but doesn't specify fallback behavior when `omp` is not on the system PATH. | Wrap fails with "command not found" — user has no guidance. | Define fallback discovery paths (`~/.bun/bin/omp`, `~/.npm-global/bin/omp`, etc.) and a `HEADROOM_OMP_BIN` env var override. |
| SG-6 | **Proxy lifecycle after OMP exits**: Spec doesn't specify whether the proxy should be kept alive or torn down when OMP exits. | If proxy stays alive, subsequent `wrap omp` calls can reuse it. If it dies, OMP requests fail silently. | Clarify: proxy runs independently of OMP (started by `wrap`, stopped by `unwrap` or explicit `headroom stop`). OMP exiting should not kill the proxy. |
| SG-7 | **Wrap manifest format**: Spec has no definition for a manifest file recording what was wrapped, which file backups exist, and what state to restore on unwrap. | `unwrap` relies on fragile file-name conventions (.headroom-backup) and marker scanning. Restore is non-deterministic in edge cases. | Define a lightweight manifest (`.omp/.headroom.json`) tracking: original file paths, backup paths, markers injected, OMP version, timestamp. |
| SG-8 | **Project-local vs user-level separation**: Spec says "project-level config written to `.omp/`" but `models.yml` lives at `~/.omp/agent/models.yml` (user-level, not project-level). | Wrap modifies user-global OMP config, not project-local. Unwrap must restore user-level state. | Clarify that `models.yml` modification operates at the user-level `~/.omp/agent/models.yml`, while `mcp.json` and `config.yml` operate at project-level `.omp/`. Document the asymmetric scope in the spec. |
