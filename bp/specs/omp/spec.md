# OMP Integration Specification

## Purpose

Oh My Pi (OMP) coding agent integration — wrapping OMP through Headroom proxy for context compression, MCP server registration, and provider routing.

## Requirements

### Requirement: Wrap command — configuration injection
The system SHALL inject Headroom proxy configuration into OMP's project-local `.omp/` directory when `headroom wrap omp` is run.

#### Scenario: Inject MCP server config
- **GIVEN** an OMP project with `.omp/mcp.json`
- **WHEN** `headroom wrap omp` is executed
- **THEN** the headroom MCP server SHALL be registered in `.omp/mcp.json`
- **AND** the original `.omp/mcp.json` SHALL be preserved in a backup

#### Scenario: Backup models.yml before modification
- **GIVEN** `~/.omp/agent/models.yml` exists with provider configurations
- **WHEN** `headroom wrap omp` is executed
- **THEN** a backup SHALL be created at `models.yml.headroom-backup`
- **AND** provider `baseUrl` entries SHALL be modified to route through Headroom proxy

#### Scenario: Config marker injection
- **GIVEN** `.omp/config.yml` exists
- **WHEN** `headroom wrap omp` is executed
- **THEN** Headroom-managed markers SHALL be injected into the config

### Requirement: Unwrap command — full restoration
The system SHALL fully restore OMP configuration to pre-wrap state when `headroom unwrap omp` is run.

#### Scenario: Restore from backup
- **GIVEN** a previous `headroom wrap omp` created backups
- **WHEN** `headroom unwrap omp` is executed
- **THEN** the backup files SHALL be restored to their original locations
- **AND** backup files SHALL be removed

#### Scenario: Clean Headroom markers
- **GIVEN** no backup file exists but Headroom markers are present
- **WHEN** `headroom unwrap omp` is executed
- **THEN** Headroom-managed blocks SHALL be stripped from config files
- **AND** non-Headroom content SHALL be preserved

#### Scenario: Skip clean config
- **GIVEN** no backup file exists and no Headroom markers are present
- **WHEN** `headroom unwrap omp` is executed
- **THEN** no changes SHALL be made

### Requirement: MCP registrar — OmpRegistrar
The system SHALL provide an MCP registrar for OMP following the `headroom/mcp_registry/` pattern.

#### Scenario: Register headroom MCP server
- **GIVEN** an OMP project with `.omp/` directory
- **WHEN** `OmpRegistrar.register_server()` is called
- **THEN** the headroom MCP server SHALL be added to `.omp/mcp.json`
- **AND** the result SHALL indicate successful registration

#### Scenario: Unregister headroom MCP server
- **GIVEN** `.omp/mcp.json` contains a headroom MCP server entry
- **WHEN** `OmpRegistrar.unregister_server("headroom")` is called
- **THEN** the headroom entry SHALL be removed from `.omp/mcp.json`

### Requirement: Launch OMP through proxy
The system SHALL launch the `omp` CLI after proxy startup and configuration injection.

#### Scenario: Launch omp binary
- **GIVEN** Headroom proxy is running and configuration is injected
- **WHEN** OMP is launched
- **THEN** LLM provider requests SHALL be routed through the Headroom proxy
- **AND** OMP SHALL have access to the headroom MCP server for content retrieval
