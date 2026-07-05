"""Tests for :class:`headroom.mcp_registry.omp.OmpRegistrar`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from headroom.mcp_registry.base import RegisterStatus, ServerSpec
from headroom.mcp_registry.omp import (
    _diff_specs,
    _entry_to_spec,
    _read_json,
    _spec_to_entry,
    _specs_equivalent,
    _write_json,
    OmpRegistrar,
)


def _write_mcp_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _registrar(tmp_path: Path) -> OmpRegistrar:
    """Create an OmpRegistrar with a config path under tmp_path."""
    config_path = tmp_path / ".omp" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    return OmpRegistrar(config_path=config_path)


# ---------------------------------------------------------------------------
# Detect
# ---------------------------------------------------------------------------


def test_detect_when_omp_dir_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Detection succeeds when the .omp directory exists."""
    monkeypatch.chdir(tmp_path)
    omp_dir = tmp_path / ".omp"
    omp_dir.mkdir()
    registrar = OmpRegistrar()
    assert registrar.detect() is True


def test_detect_when_nothing_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Detection fails when .omp directory does not exist."""
    monkeypatch.chdir(tmp_path)
    registrar = OmpRegistrar()
    assert registrar.detect() is False


# ---------------------------------------------------------------------------
# Get server
# ---------------------------------------------------------------------------


def test_get_server_returns_none_when_absent(tmp_path: Path) -> None:
    """get_server returns None when the server is not configured."""
    registrar = _registrar(tmp_path)
    assert registrar.get_server("headroom") is None


def test_get_server_returns_spec_when_present(tmp_path: Path) -> None:
    """get_server parses the existing MCP entry correctly."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {
        "mcpServers": {
            "headroom": {
                "command": "headroom",
                "args": ["mcp", "serve"],
                "env": {"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"},
            },
        },
    })
    registrar = _registrar(tmp_path)
    spec = registrar.get_server("headroom")
    assert spec is not None
    assert spec.name == "headroom"
    assert spec.command == "headroom"
    assert spec.args == ["mcp", "serve"]
    assert spec.env == {"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"}


def test_get_server_returns_none_for_non_dict_mcp(tmp_path: Path) -> None:
    """get_server returns None when 'mcpServers' is not a dict."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {"mcpServers": "not-a-dict"})
    registrar = _registrar(tmp_path)
    assert registrar.get_server("headroom") is None


def test_get_server_handles_missing_config_file(tmp_path: Path) -> None:
    """get_server returns None when the config file doesn't exist."""
    registrar = _registrar(tmp_path)
    assert registrar.get_server("headroom") is None


# ---------------------------------------------------------------------------
# Register server
# ---------------------------------------------------------------------------


def test_register_server_creates_config_when_missing(tmp_path: Path) -> None:
    """register_server creates the config file when it doesn't exist."""
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    result = registrar.register_server(spec)
    assert result.status == RegisterStatus.REGISTERED
    config_path = tmp_path / ".omp" / "mcp.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["headroom"]["command"] == "headroom"


def test_register_server_idempotent(tmp_path: Path) -> None:
    """register_server is a no-op when the same spec is already present."""
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec)
    result = registrar.register_server(spec)
    assert result.status == RegisterStatus.ALREADY


def test_register_server_force_overwrites_mismatch(tmp_path: Path) -> None:
    """register_server with force=True overwrites a mismatched existing server."""
    registrar = _registrar(tmp_path)
    spec1 = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec1)
    spec2 = ServerSpec(name="headroom", command="headroom2", args=["serve"])
    result = registrar.register_server(spec2, force=True)
    assert result.status == RegisterStatus.REGISTERED
    updated = registrar.get_server("headroom")
    assert updated is not None
    assert updated.command == "headroom2"


def test_register_server_returns_mismatch_without_force(tmp_path: Path) -> None:
    """register_server returns MISMATCH when spec differs and force is False."""
    registrar = _registrar(tmp_path)
    spec1 = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec1)
    spec2 = ServerSpec(name="headroom", command="headroom2", args=["serve"])
    result = registrar.register_server(spec2)
    assert result.status == RegisterStatus.MISMATCH


def test_register_server_preserves_other_mcp_servers(tmp_path: Path) -> None:
    """register_server preserves other MCP servers in the config."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {
        "mcpServers": {
            "existing-server": {
                "command": "existing",
                "args": [],
            },
        },
    })
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec)
    data = json.loads(config_path.read_text())
    assert "existing-server" in data["mcpServers"]
    assert "headroom" in data["mcpServers"]


def test_register_server_handles_config_with_no_mcp_key(tmp_path: Path) -> None:
    """register_server adds 'mcpServers' key when it doesn't exist."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {"other": "data"})
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec)
    data = json.loads(config_path.read_text())
    assert "headroom" in data["mcpServers"]


def test_register_server_with_env_vars(tmp_path: Path) -> None:
    """register_server handles ServerSpec with environment variables."""
    registrar = _registrar(tmp_path)
    spec = ServerSpec(
        name="headroom",
        command="headroom",
        args=["mcp", "serve"],
        env={"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"},
    )
    registrar.register_server(spec)
    config_path = tmp_path / ".omp" / "mcp.json"
    data = json.loads(config_path.read_text())
    assert data["mcpServers"]["headroom"]["env"] == {"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"}


def test_register_server_on_malformed_config_file(tmp_path: Path) -> None:
    """register_server overwrites a malformed config file."""
    config_path = tmp_path / ".omp" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("not valid json\n")
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    result = registrar.register_server(spec)
    assert result.status == RegisterStatus.REGISTERED
    data = json.loads(config_path.read_text())
    assert "headroom" in data["mcpServers"]


# ---------------------------------------------------------------------------
# Unregister server
# ---------------------------------------------------------------------------


def test_unregister_server_removes_entry(tmp_path: Path) -> None:
    """unregister_server removes the server entry."""
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec)
    assert registrar.get_server("headroom") is not None
    registrar.unregister_server("headroom")
    assert registrar.get_server("headroom") is None


def test_unregister_server_returns_true_when_absent(tmp_path: Path) -> None:
    """unregister_server returns True when the server was not registered (idempotent)."""
    registrar = _registrar(tmp_path)
    assert registrar.unregister_server("headroom") is True


def test_unregister_removes_mcp_key_when_empty(tmp_path: Path) -> None:
    """unregister_server removes the 'mcpServers' key when it becomes empty."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {
        "other_key": "value",
        "mcpServers": {
            "headroom": {
                "command": "headroom",
                "args": ["mcp", "serve"],
            },
        },
    })
    registrar = _registrar(tmp_path)
    registrar.unregister_server("headroom")
    data = json.loads(config_path.read_text())
    assert "mcpServers" not in data
    assert data.get("other_key") == "value"



def test_unregister_preserves_other_mcp_servers(tmp_path: Path) -> None:
    """unregister_server leaves other MCP servers intact."""
    config_path = tmp_path / ".omp" / "mcp.json"
    _write_mcp_json(config_path, {
        "mcpServers": {
            "headroom": {
                "command": "headroom",
                "args": ["mcp", "serve"],
            },
            "other-server": {
                "command": "other",
                "args": [],
            },
        },
    })
    registrar = _registrar(tmp_path)
    registrar.unregister_server("headroom")
    data = json.loads(config_path.read_text())
    assert "other-server" in data["mcpServers"]
    assert "headroom" not in data["mcpServers"]


def test_unregister_server_handles_oserror(tmp_path: Path) -> None:
    """unregister_server returns False on OSError."""
    registrar = _registrar(tmp_path)
    spec = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    registrar.register_server(spec)
    # Add a non-mcpServers key so the file isn't removed entirely
    config_path = tmp_path / ".omp" / "mcp.json"
    data = json.loads(config_path.read_text())
    data["other_key"] = "value"
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    with patch("headroom.mcp_registry.omp.json.dump", side_effect=OSError("read-only filesystem")):
        ok = registrar.unregister_server("headroom")
        assert ok is False


def test_entry_to_spec_no_command() -> None:
    """_entry_to_spec handles an entry without a 'command' key."""
    entry = {"args": ["serve"]}
    spec = _entry_to_spec("headroom", entry)
    assert spec.command == ""


def test_entry_to_spec_reads_environment(tmp_path: Path) -> None:
    """_entry_to_spec reads the environment map."""
    entry = {
        "command": "headroom",
        "args": ["mcp", "serve"],
        "env": {"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"},
    }
    spec = _entry_to_spec("headroom", entry)
    assert spec.env == {"HEADROOM_PROXY_URL": "http://127.0.0.1:9090"}


def test_spec_to_entry_roundtrip() -> None:
    """_spec_to_entry and _entry_to_spec are inverses."""
    original = ServerSpec(
        name="headroom",
        command="headroom",
        args=["mcp", "serve"],
        env={"KEY": "value"},
    )
    entry = _spec_to_entry(original)
    restored = _entry_to_spec("headroom", entry)
    assert restored.name == original.name
    assert restored.command == original.command
    assert restored.args == original.args
    assert restored.env == original.env


# ---------------------------------------------------------------------------
# Specs equivalent / Diff specs
# ---------------------------------------------------------------------------


def test_specs_equivalent_true() -> None:
    """_specs_equivalent returns True for identical specs."""
    a = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    b = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    assert _specs_equivalent(a, b) is True


def test_specs_equivalent_false() -> None:
    """_specs_equivalent returns False for different specs."""
    a = ServerSpec(name="headroom", command="headroom", args=["mcp", "serve"])
    b = ServerSpec(name="headroom", command="headroom2", args=["serve"])
    assert _specs_equivalent(a, b) is False


def test_diff_specs_all_fields() -> None:
    """_diff_specs reports differences in all fields."""
    a = ServerSpec(name="headroom", command="a", args=["a1"], env={"K": "v1"})
    b = ServerSpec(name="headroom", command="b", args=["b1"], env={"K": "v2"})
    diff = _diff_specs(a, b)
    assert "a" in diff
    assert "b" in diff
    assert "a1" in diff
    assert "b1" in diff


def test_diff_specs_no_difference_returns_empty_string() -> None:
    """_diff_specs returns empty string when no identifiable field differs."""
    a = ServerSpec(name="headroom", command="headroom", args=())
    b = ServerSpec(name="headroom", command="headroom", args=())
    diff = _diff_specs(a, b)
    assert diff == ""


def test_write_json_creates_parent_dirs(tmp_path: Path) -> None:
    """_write_json creates parent directories."""
    path = tmp_path / "a" / "b" / "c" / "test.json"
    _write_json(path, {"key": "value"})
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == {"key": "value"}
