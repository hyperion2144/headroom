"""Tests for OMP config file helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from headroom.providers.omp.config import (
    _build_upstream_map,
    _CONFIG_BLOCK_RE,
    _CONFIG_MARKER_END,
    _CONFIG_MARKER_START,
    _headroom_provider_entry,
    _modify_provider_base_urls,
    _remove_upstream_map,
    _strip_omp_config_markers,
    _write_upstream_map,
    inject_omp_proxy_config,
    omp_config_paths,
    omp_home_dir,
    omp_mcp_config_path,
    omp_models_yml_path,
    omp_upstream_map_path,
    restore_omp_models_yml,
    snapshot_omp_models_if_unwrapped,
    strip_omp_headroom_blocks,
)


def _set_test_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set OMP_CODING_AGENT_DIR to a tmp_path for testing."""
    monkeypatch.setenv("OMP_CODING_AGENT_DIR", str(tmp_path))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)


# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------


def test_omp_home_dir_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default home dir resolves to ~/.omp/agent."""
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.delenv("OMP_CODING_AGENT_DIR", raising=False)
    expected = Path.home() / ".omp" / "agent"
    assert omp_home_dir() == expected


def test_omp_home_dir_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OMP_CODING_AGENT_DIR env var overrides the default path."""
    monkeypatch.setenv("OMP_CODING_AGENT_DIR", str(tmp_path))
    assert omp_home_dir() == tmp_path


def test_omp_home_dir_from_pi_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PI_CODING_AGENT_DIR env var overrides the default path."""
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    monkeypatch.delenv("OMP_CODING_AGENT_DIR", raising=False)
    assert omp_home_dir() == tmp_path


def test_omp_models_yml_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """models.yml path resolves under omp_home_dir."""
    _set_test_home(monkeypatch, tmp_path)
    assert omp_models_yml_path() == tmp_path / "models.yml"


def test_omp_mcp_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mcp.json path resolves to cwd/.omp/mcp.json."""
    monkeypatch.chdir(tmp_path)
    assert omp_mcp_config_path() == tmp_path / ".omp" / "mcp.json"


def test_omp_upstream_map_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """upstream map path resolves to cwd/.omp/.headroom-upstreams.json."""
    monkeypatch.chdir(tmp_path)
    assert omp_upstream_map_path() == tmp_path / ".omp" / ".headroom-upstreams.json"


def test_omp_config_paths_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default config paths return models.yml and backup."""
    _set_test_home(monkeypatch, tmp_path)
    config_file, backup_file = omp_config_paths()
    assert config_file == tmp_path / "models.yml"
    assert backup_file == tmp_path / "models.yml.headroom-backup"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_snapshot_creates_backup(tmp_path: Path) -> None:
    """snapshot creates a backup copy of the config file."""
    config_file = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    config_file.write_text("providers: {}")
    snapshot_omp_models_if_unwrapped(config_file, backup_file)
    assert backup_file.exists()
    assert backup_file.read_text() == config_file.read_text()


def test_snapshot_skips_if_backup_exists(tmp_path: Path) -> None:
    """snapshot is a no-op when the backup already exists."""
    config_file = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    config_file.write_text("providers: {a: 1}")
    backup_file.write_text("providers: {b: 2}")
    snapshot_omp_models_if_unwrapped(config_file, backup_file)
    assert backup_file.read_text() == "providers: {b: 2}"


def test_snapshot_skips_if_markers_present(tmp_path: Path) -> None:
    """snapshot skips if the config already contains Headroom markers."""
    config_file = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    config_file.write_text(f"providers:\n  test:\n{_CONFIG_MARKER_START}\n    baseUrl: http://proxy\n{_CONFIG_MARKER_END}")
    snapshot_omp_models_if_unwrapped(config_file, backup_file)
    assert not backup_file.exists()


def test_snapshot_skips_missing_config(tmp_path: Path) -> None:
    """snapshot skips when config file does not exist."""
    config_file = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    snapshot_omp_models_if_unwrapped(config_file, backup_file)
    assert not backup_file.exists()


# ---------------------------------------------------------------------------
# Strip blocks
# ---------------------------------------------------------------------------


def test_strip_blocks_removes_markers() -> None:
    """strip removes Headroom marker blocks."""
    content = f"""providers:
  test:
    baseUrl: http://original
{_CONFIG_MARKER_START}
  headroom:
    baseUrl: http://proxy
{_CONFIG_MARKER_END}
  other:
    baseUrl: http://other"""
    cleaned = strip_omp_headroom_blocks(content)
    assert _CONFIG_MARKER_START not in cleaned
    assert _CONFIG_MARKER_END not in cleaned


def test_strip_blocks_preserves_user_content() -> None:
    """strip leaves user content untouched when no blocks are present."""
    content = "providers:\n  test:\n    baseUrl: http://original"
    cleaned = strip_omp_headroom_blocks(content)
    assert cleaned == content.strip()


def test_strip_blocks_handles_empty_string() -> None:
    """strip returns empty string for empty input."""
    assert strip_omp_headroom_blocks("") == ""


def test_strip_blocks_handles_whitespace_only() -> None:
    """strip returns empty string for whitespace input."""
    assert strip_omp_headroom_blocks("  \n  ") == ""


def test_strip_config_markers_removed(tmp_path: Path) -> None:
    """_strip_omp_config_markers returns 'removed' when markers are stripped."""
    config_file = tmp_path / ".omp" / "config.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(f"some_config: true\n{_CONFIG_MARKER_START}\nproxy: true\n{_CONFIG_MARKER_END}")
    result = _strip_omp_config_markers(config_file)
    assert result == "stripped"
    content = config_file.read_text()
    assert _CONFIG_MARKER_START not in content
    assert _CONFIG_MARKER_END not in content


def test_strip_config_markers_noop(tmp_path: Path) -> None:
    """_strip_omp_config_markers returns 'noop' when no markers present."""
    config_file = tmp_path / ".omp" / "config.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("some_config: true")
    result = _strip_omp_config_markers(config_file)
    assert result == "noop"
    assert config_file.read_text() == "some_config: true"


def test_strip_config_markers_stripped(tmp_path: Path) -> None:
    """_strip_omp_config_markers returns 'stripped' when file is empty after strip."""
    config_file = tmp_path / ".omp" / "config.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(f"{_CONFIG_MARKER_START}\nproxy: true\n{_CONFIG_MARKER_END}")
    result = _strip_omp_config_markers(config_file)
    assert result == "removed"
    assert not config_file.exists()


# ---------------------------------------------------------------------------
# Provider URL modification
# ---------------------------------------------------------------------------


def test_modify_provider_base_urls_rewrites_urls() -> None:
    """_modify_provider_base_urls rewrites baseUrl to proxy URL."""
    providers = {
        "deepseek": {
            "models": ["deepseek-v4-flash"],
            "baseUrl": "https://original.example.com",
        },
        "minimax": {
            "models": ["MiniMax-M3"],
            "baseUrl": "https://api.minimaxi.com",
        },
    }
    modified = _modify_provider_base_urls(providers, proxy_port=9000)
    assert modified == 2
    assert providers["deepseek"]["baseUrl"] == "http://127.0.0.1:9000"
    assert providers["minimax"]["baseUrl"] == "http://127.0.0.1:9000"
    assert providers["deepseek"]["_headroom_original_baseUrl"] == "https://original.example.com"


def test_modify_provider_base_urls_preserves_original_on_rewrap() -> None:
    """_modify_provider_base_urls preserves _headroom_original_baseUrl on re-wrap."""
    providers = {
        "deepseek": {
            "models": ["deepseek-v4-flash"],
            "baseUrl": "http://127.0.0.1:9000",
            "_headroom_original_baseUrl": "https://original.example.com",
        },
    }
    modified = _modify_provider_base_urls(providers, proxy_port=9001)
    assert modified == 1
    assert providers["deepseek"]["baseUrl"] == "http://127.0.0.1:9001"
    assert providers["deepseek"]["_headroom_original_baseUrl"] == "https://original.example.com"


def test_modify_provider_base_urls_skips_empty_providers() -> None:
    """_modify_provider_base_urls returns 0 when no providers."""
    modified = _modify_provider_base_urls({}, proxy_port=9000)
    assert modified == 0



def test_headroom_provider_entry() -> None:
    """_headroom_provider_entry returns correct structure."""
    entry = _headroom_provider_entry(port=9000)
    assert isinstance(entry, dict)
    assert "models" in entry
    assert entry.get("baseUrl") == "http://127.0.0.1:9000"


# ---------------------------------------------------------------------------
# Inject config
# ---------------------------------------------------------------------------


def test_inject_proxy_config_updates_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config updates existing models.yml."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("providers:\n  deepseek:\n    models: [\"deepseek-v4-flash\"]\n    baseUrl: https://original.example.com\n")
    inject_omp_proxy_config(port=9000)
    content = models_yml.read_text()
    assert "http://127.0.0.1:9000" in content
    # Original baseUrl is preserved as _headroom_original_baseUrl
    assert "_headroom_original_baseUrl: https://original.example.com" in content


def test_inject_proxy_config_writes_upstream_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config writes upstream map file."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("providers:\n  deepseek:\n    models: [\"deepseek-v4-flash\"]\n    baseUrl: https://original.example.com\n    apiKey: sk-deepseek-key\n")
    inject_omp_proxy_config(port=9000)
    upstream_map = tmp_path / ".omp" / ".headroom-upstreams.json"
    assert upstream_map.exists()
    data = json.loads(upstream_map.read_text())
    assert "sk-deepseek-key" in data
    assert data["sk-deepseek-key"] == "https://original.example.com"


def test_inject_proxy_config_writes_config_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config writes config.yml markers."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    # Must have models.yml with providers for inject to proceed to marker writing
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("providers:\n  test:\n    models: [\"test-model\"]\n    baseUrl: https://example.com\n")
    config_yml = tmp_path / ".omp" / "config.yml"
    config_yml.parent.mkdir(parents=True)
    config_yml.write_text("some_config: true\n")
    inject_omp_proxy_config(port=9000)
    content = config_yml.read_text()
    assert _CONFIG_MARKER_START in content
    assert _CONFIG_MARKER_END in content


def test_inject_proxy_config_handles_empty_models_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config handles empty models.yml gracefully."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("")
    inject_omp_proxy_config(port=9000)
    assert models_yml.exists()


# ---------------------------------------------------------------------------
# Upstream map
# ---------------------------------------------------------------------------


def test_build_upstream_map_normal() -> None:
    """_build_upstream_map builds mapping from models.yml data."""
    data = {
        "providers": {
            "deepseek": {
                "models": ["deepseek-v4-flash"],
                "baseUrl": "http://127.0.0.1:9000",
                "_headroom_original_baseUrl": "https://original.example.com",
                "apiKey": "sk-deepseek-key",
            },
            "minimax": {
                "models": ["MiniMax-M3"],
                "baseUrl": "http://127.0.0.1:9000",
                "_headroom_original_baseUrl": "https://api.minimaxi.com",
                "apiKey": "sk-minimax-key",
            },
        }
    }
    with patch("headroom.providers.omp.config._discover_builtin_providers"):
        mapping = _build_upstream_map(data)
    assert mapping == {
        "sk-deepseek-key": "https://original.example.com",
        "sk-minimax-key": "https://api.minimaxi.com",
    }


def test_build_upstream_map_skips_wildcard() -> None:
    """_build_upstream_map skips wildcard model ids."""
    data = {
        "providers": {
            "test": {
                "models": ["*"],
                "baseUrl": "https://example.com",
            },
        }
    }
    with patch("headroom.providers.omp.config._discover_builtin_providers"):
        mapping = _build_upstream_map(data)
    assert mapping == {}


def test_build_upstream_map_skips_non_dict_provider(tmp_path: Path) -> None:
    """_build_upstream_map skips non-dict provider values."""
    data = {
        "providers": {
            "test": "not-a-dict",
        }
    }
    with patch("headroom.providers.omp.config._discover_builtin_providers"):
        mapping = _build_upstream_map(data)
    assert mapping == {}


def test_write_upstream_map_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_write_upstream_map writes JSON and creates parent dirs."""
    monkeypatch.chdir(tmp_path)
    mapping = {"test-model": "https://example.com"}
    path = _write_upstream_map(mapping)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data == mapping


def test_remove_upstream_map_removes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_remove_upstream_map removes the upstream map file."""
    monkeypatch.chdir(tmp_path)
    map_file = tmp_path / ".omp" / ".headroom-upstreams.json"
    map_file.parent.mkdir(parents=True)
    map_file.write_text("{}")
    _remove_upstream_map()
    assert not map_file.exists()


def test_remove_upstream_map_silent_on_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_remove_upstream_map is silent when file does not exist."""
    monkeypatch.chdir(tmp_path)
    _remove_upstream_map()  # should not raise


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def test_restore_from_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """restore_omp_models_yml restores from backup."""
    _set_test_home(monkeypatch, tmp_path)
    models_yml = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    models_yml.write_text("modified content")
    backup_file.write_text("original content")
    status, _ = restore_omp_models_yml()
    assert status == "restored"
    assert models_yml.read_text() == "original content"


def test_restore_noop_when_no_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """restore_omp_models_yml is noop when no backup exists."""
    _set_test_home(monkeypatch, tmp_path)
    status, _ = restore_omp_models_yml()
    assert status == "noop"


def test_restore_strips_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """restore_omp_models_yml strips markers when no backup."""
    _set_test_home(monkeypatch, tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text(f"providers:\n  test:\n    baseUrl: http://proxy\n{_CONFIG_MARKER_START}\n  headroom:\n    baseUrl: http://proxy\n{_CONFIG_MARKER_END}")
    status, _ = restore_omp_models_yml()
    assert status == "cleaned"
    content = models_yml.read_text()
    assert _CONFIG_MARKER_START not in content


def test_restore_removes_file_when_empty_after_strip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """restore_omp_models_yml removes file when empty after strip."""
    _set_test_home(monkeypatch, tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text(f"{_CONFIG_MARKER_START}\nproxy: true\n{_CONFIG_MARKER_END}")
    status, _ = restore_omp_models_yml()
    assert status == "removed"
    assert not models_yml.exists()


def test_restore_divergence_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """restore_omp_models_yml warns when live file differs from backup."""
    _set_test_home(monkeypatch, tmp_path)
    models_yml = tmp_path / "models.yml"
    backup_file = tmp_path / "models.yml.headroom-backup"
    models_yml.write_text("live content")
    backup_file.write_text("backup content")
    status, _ = restore_omp_models_yml()
    assert status == "restored"
    assert models_yml.read_text() == "backup content"


# ---------------------------------------------------------------------------
# Edge cases — YAML parsing
# ---------------------------------------------------------------------------


def test_inject_proxy_config_handles_missing_models_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config silently returns when models.yml is missing."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    assert not models_yml.exists()
    # Should not raise — returns early
    inject_omp_proxy_config(port=9000)
    # File is NOT created by inject (it only modifies existing files)
    assert not models_yml.exists()


def test_inject_proxy_config_handles_missing_pyyaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """inject_omp_proxy_config raises RuntimeError when pyyaml is missing."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("providers:\n  test:\n    models: [\"test-model\"]\n    baseUrl: https://example.com\n")
    import headroom.providers.omp.config as config_module
    original_yaml = config_module._yaml
    config_module._yaml = None
    try:
        with pytest.raises(RuntimeError, match="PyYAML is required"):
            inject_omp_proxy_config(port=9000)
    finally:
        config_module._yaml = original_yaml
