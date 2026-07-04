"""OMP MCP registrar.

Register and unregister the Headroom MCP server with OMP (Oh My Pi) via
the project-local ``.omp/mcp.json`` file (``mcpServers`` key, matching the
VSCode/Cursor convention that OMP uses).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .base import MCPRegistrar, RegisterResult, RegisterStatus, ServerSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Low-level JSON helpers (mirror OpencodeRegistrar)
# ---------------------------------------------------------------------------


def _omp_mcp_config_path() -> Path:
    """Return the project-local OMP MCP config path."""
    return Path.cwd() / ".omp" / "mcp.json"


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict if absent or unparseable."""
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _entry_to_spec(name: str, entry: dict[str, Any]) -> ServerSpec:
    """Convert an ``mcpServers`` entry to a ``ServerSpec``."""
    command = entry.get("command")
    if not command:
        return ServerSpec(name=name, command="")
    args = entry.get("args") or []
    env = entry.get("env") or {}
    return ServerSpec(name=name, command=command, args=list(args), env=dict(env))


def _spec_to_entry(spec: ServerSpec) -> dict[str, Any]:
    """Convert a ``ServerSpec`` to an ``mcpServers`` entry dict."""
    entry: dict[str, Any] = {
        "command": spec.command,
    }
    if spec.args:
        entry["args"] = list(spec.args)
    if spec.env:
        entry["env"] = dict(spec.env)
    return entry


def _specs_equivalent(a: ServerSpec, b: ServerSpec) -> bool:
    """Return True when two specs describe the same MCP server."""
    return (
        a.name == b.name
        and a.command == b.command
        and a.args == b.args
        and a.env == b.env
    )


def _diff_specs(existing: ServerSpec, requested: ServerSpec) -> str:
    """Describe the differences between two specs."""
    parts: list[str] = []
    if existing.command != requested.command:
        parts.append(f"command: {existing.command!r} -> {requested.command!r}")
    if existing.args != requested.args:
        parts.append(f"args: {existing.args} -> {requested.args}")
    if existing.env != requested.env:
        parts.append(f"env: {existing.env} -> {requested.env}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# OMP MCP Registrar
# ---------------------------------------------------------------------------


class OmpRegistrar(MCPRegistrar):
    """Register MCP servers with OMP via project-local ``.omp/mcp.json``.

    OMP's format mirrors the VSCode/Cursor convention: a top-level
    ``mcpServers`` map, where each key is a server name and the value
    has ``command``, optional ``args``, and optional ``env``.
    """

    name: str = "omp"
    display_name: str = "OMP"

    def __init__(self, *, config_path: Path | None = None) -> None:
        self._config_path: Path = config_path or _omp_mcp_config_path()

    def detect(self) -> bool:
        """Return True when a ``.omp/`` directory exists at the project root."""
        return self._config_path.parent.is_dir()

    def get_server(self, server_name: str) -> ServerSpec | None:
        """Return the registered ``ServerSpec`` for ``server_name``, or None."""
        data = _read_json(self._config_path)
        servers = data.get("mcpServers") or {}
        entry = servers.get(server_name)
        if not entry or not isinstance(entry, dict):
            return None
        return _entry_to_spec(server_name, entry)

    def register_server(  # type: ignore[override]
        self,
        spec: ServerSpec,
        *,
        force: bool = False,
    ) -> RegisterResult:
        """Register ``spec`` under ``mcpServers`` in OMP's MCP config.

        If a server with the same name already exists:
        - ``force=False`` and configs match → ``ALREADY``
        - ``force=False`` and configs differ → ``MISMATCH`` (no change)
        - ``force=True`` → overwrite with the new spec and return ``REGISTERED``
        """
        if not self.detect():
            return RegisterResult(
                RegisterStatus.NOT_DETECTED,
                f"no .omp/ directory found at {self._config_path.parent}",
            )

        data = _read_json(self._config_path)
        servers: dict[str, Any] = data.get("mcpServers") or {}

        if spec.name in servers:
            existing = _entry_to_spec(spec.name, servers[spec.name])
            if _specs_equivalent(existing, spec):
                return RegisterResult(
                    RegisterStatus.ALREADY,
                    f"{spec.name} already registered in {self._config_path}",
                )
            if not force:
                diff = _diff_specs(existing, spec)
                return RegisterResult(
                    RegisterStatus.MISMATCH,
                    f"{spec.name} differs: {diff}",
                )
            logger.info("Overwriting existing %s entry in %s", spec.name, self._config_path)

        servers[spec.name] = _spec_to_entry(spec)
        data["mcpServers"] = servers

        try:
            _write_json(self._config_path, data)
        except OSError as exc:
            return RegisterResult(
                RegisterStatus.FAILED,
                f"could not write to {self._config_path}: {exc}",
            )

        verb = "overwrote" if spec.name in servers and force else "wrote"
        return RegisterResult(
            RegisterStatus.REGISTERED,
            f"{verb} {spec.name} to {self._config_path}",
        )

    def unregister_server(self, server_name: str) -> bool:
        """Remove ``server_name`` from ``mcpServers`` in OMP's MCP config.

        Returns True when the server was removed or absent, False on error.
        """
        try:
            data = _read_json(self._config_path)
            servers: dict[str, Any] = data.get("mcpServers") or {}
            if server_name not in servers:
                return True

            del servers[server_name]
            if servers:
                data["mcpServers"] = servers
            else:
                # Remove the empty mcpServers map to keep the file clean.
                data.pop("mcpServers", None)
                # If nothing remains, remove the file entirely.
                if not data or data.keys() == {"$schema"}:
                    self._config_path.unlink(missing_ok=True)
                    return True

            _write_json(self._config_path, data)
            return True
        except OSError:
            return False
