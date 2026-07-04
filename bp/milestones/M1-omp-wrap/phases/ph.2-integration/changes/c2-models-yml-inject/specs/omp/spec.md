# Delta-Spec: omp

> Change: c2-models-yml-inject | Domain: omp

This delta extends the global `bp/specs/omp/spec.md` with the models.yml injection refinements (original-baseUrl preservation, re-wrap idempotency) and the new upstream-mapping contract (generation + cleanup) that connects config.py to the c3 proxy router. The global spec's existing "Wrap command — configuration injection" and "Unwrap command — full restoration" requirements remain in force; the requirements below make their models.yml-specific behaviors precise and add the mapping-file lifecycle.

## ADDED Requirements

### Requirement: Upstream mapping file generation
The system SHALL generate a project-local mapping file `.omp/.headroom-upstreams.json` during `inject_omp_proxy_config` that maps every concrete model id to its provider's original upstream `baseUrl`, derived from the `_headroom_original_baseUrl` field stored on each modified provider.

#### Scenario: Generate mapping from modified providers
- **GIVEN** `models.yml` with providers that each declare a `baseUrl`, an `api`, and a `models` list of concrete ids
- **WHEN** `inject_omp_proxy_config(port)` is executed
- **THEN** `.omp/.headroom-upstreams.json` SHALL be written containing one entry per model id mapped to that provider's pre-wrap `baseUrl`
- **AND** the file SHALL be valid JSON with sorted keys

#### Scenario: Skip wildcard models
- **GIVEN** a provider whose `models` list contains a wildcard id `"*"`
- **WHEN** the upstream mapping is built
- **THEN** the wildcard id SHALL be omitted from the mapping (no upstream can be resolved for an unknown model set)

#### Scenario: Skip providers without a stored original
- **GIVEN** a provider that has no `_headroom_original_baseUrl` field (e.g. a provider without a `baseUrl` to rewrite)
- **WHEN** the upstream mapping is built
- **THEN** that provider's models SHALL be omitted from the mapping

#### Scenario: Empty mapping when no providers modified
- **GIVEN** `models.yml` with no `providers` or no provider carrying a `baseUrl`
- **WHEN** `inject_omp_proxy_config(port)` is executed
- **THEN** no `.omp/.headroom-upstreams.json` SHALL be written (the mapping step is skipped when zero providers are modified)

### Requirement: Original baseUrl preservation
The system SHALL preserve each provider's pre-wrap upstream `baseUrl` in a `_headroom_original_baseUrl` field at injection time so the proxy can later route to the true upstream.

#### Scenario: Capture original on first wrap
- **GIVEN** a provider with `baseUrl: "https://ark.cn-beijing.volces.com/api/plan/v3"`
- **WHEN** `inject_omp_proxy_config(port)` is executed
- **THEN** the provider's `baseUrl` SHALL become `http://127.0.0.1:{port}`
- **AND** `_headroom_original_baseUrl` SHALL equal `https://ark.cn-beijing.volces.com/api/plan/v3`

### Requirement: Re-wrap idempotency
The system SHALL be idempotent: re-running `inject_omp_proxy_config` on an already-wrapped `models.yml` SHALL NOT overwrite `_headroom_original_baseUrl` with the proxy URL, and SHALL NOT duplicate or corrupt the upstream mapping.

#### Scenario: Second wrap preserves the true original
- **GIVEN** `models.yml` already wrapped once (provider `baseUrl` is the proxy URL, `_headroom_original_baseUrl` holds the true upstream)
- **WHEN** `inject_omp_proxy_config(new_port)` is executed a second time
- **THEN** the provider's `baseUrl` SHALL update to `http://127.0.0.1:{new_port}`
- **AND** `_headroom_original_baseUrl` SHALL remain the true pre-wrap upstream (NOT the previous proxy URL)
- **AND** `.omp/.headroom-upstreams.json` SHALL still map each model id to the true upstream

### Requirement: Backup divergence warning on unwrap
The system SHALL warn the user before overwriting a live `models.yml` from backup when the two files differ, without blocking the restoration.

#### Scenario: Warn when live file was edited post-wrap
- **GIVEN** a pre-wrap backup exists AND the live `models.yml` content differs from the backup
- **WHEN** `restore_omp_models_yml()` is executed
- **THEN** a warning SHALL be emitted to stderr naming both files and noting local edits will be overwritten
- **AND** the restore SHALL proceed (backup copied over the live file, backup removed)

#### Scenario: No warning when files match
- **GIVEN** a pre-wrap backup exists AND the live `models.yml` is byte-identical to the backup
- **WHEN** `restore_omp_models_yml()` is executed
- **THEN** no divergence warning SHALL be emitted
- **AND** the restore SHALL proceed normally

### Requirement: Upstream mapping cleanup on unwrap
The system SHALL remove `.omp/.headroom-upstreams.json` when unwrapping a configuration that was actually modified, and SHALL leave it untouched when unwrap is a no-op.

#### Scenario: Remove mapping after restore from backup
- **GIVEN** `.omp/.headroom-upstreams.json` exists AND a backup is restored
- **WHEN** `restore_omp_models_yml()` is executed
- **THEN** `.omp/.headroom-upstreams.json` SHALL be deleted

#### Scenario: Remove mapping after marker strip
- **GIVEN** `.omp/.headroom-upstreams.json` exists AND no backup exists but Headroom markers are present in `models.yml`
- **WHEN** `restore_omp_models_yml()` is executed (strip path)
- **THEN** `.omp/.headroom-upstreams.json` SHALL be deleted

#### Scenario: Preserve mapping on noop restore
- **GIVEN** no backup exists, no Headroom markers in `models.yml`, but `.omp/.headroom-upstreams.json` happens to be present
- **WHEN** `restore_omp_models_yml()` is executed (noop path)
- **THEN** `.omp/.headroom-upstreams.json` SHALL NOT be deleted (noop must not touch the filesystem)

#### Scenario: Missing mapping file is a no-op
- **GIVEN** a restore that modifies `models.yml` but `.omp/.headroom-upstreams.json` does not exist
- **WHEN** `restore_omp_models_yml()` is executed
- **THEN** no error SHALL be raised for the absent mapping file
