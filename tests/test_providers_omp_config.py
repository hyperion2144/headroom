"""Tests for OMP config file helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from headroom.providers.omp.config import (
    _CONFIG_BLOCK_RE,
    _CONFIG_MARKER_END,
    _CONFIG_MARKER_START,
    omp_home_dir,
    omp_mcp_config_path,
    strip_omp_headroom_blocks,
)


def test_omp_home_dir_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default home dir resolves to ~/.omp/agent."""
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


def test_omp_mcp_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mcp.json path resolves under omp_home_dir."""
    monkeypatch.setenv("OMP_CODING_AGENT_DIR", str(tmp_path))
    assert omp_mcp_config_path() == tmp_path / "mcp.json"


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
