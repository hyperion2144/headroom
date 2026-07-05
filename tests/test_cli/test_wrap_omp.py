"""Tests for `headroom wrap omp` and `headroom unwrap omp`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from headroom.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _set_test_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set OMP_CODING_AGENT_DIR to a tmp_path for testing."""
    monkeypatch.setenv("OMP_CODING_AGENT_DIR", str(tmp_path))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)


# ---------------------------------------------------------------------------
# Wrap omp
# ---------------------------------------------------------------------------


def test_wrap_omp_missing_binary_errors_clearly(runner: CliRunner) -> None:
    """If the omp binary is missing the command must fail with a clear error."""
    with patch("headroom.cli.wrap.shutil.which", return_value=None):
        result = runner.invoke(main, ["wrap", "omp"])
    assert result.exit_code != 0
    assert "not found in PATH" in result.output


def test_wrap_omp_prepare_only_does_not_require_binary(runner: CliRunner) -> None:
    """`wrap omp --prepare-only` does not require the omp binary."""
    with patch("headroom.cli.wrap.shutil.which", return_value="/usr/bin/omp"):
        with patch("headroom.cli.wrap._setup_headroom_mcp"):
            result = runner.invoke(main, ["wrap", "omp", "--prepare-only"])
    assert result.exit_code == 0, result.output
    assert "preparation complete" in result.output


def test_wrap_omp_no_mcp_skips_mcp_injection(runner: CliRunner) -> None:
    """`--no-mcp` skips MCP server injection."""
    with patch("headroom.cli.wrap.shutil.which", return_value="/usr/bin/omp"):
        with patch("headroom.cli.wrap._setup_headroom_mcp") as mock_mcp:
            result = runner.invoke(main, ["wrap", "omp", "--prepare-only", "--no-mcp"])
    assert result.exit_code == 0, result.output
    mock_mcp.assert_not_called()


def test_wrap_omp_sets_up_mcp_by_default(runner: CliRunner) -> None:
    """MCP is set up by default."""
    with patch("headroom.cli.wrap.shutil.which", return_value="/usr/bin/omp"):
        with patch("headroom.cli.wrap._setup_headroom_mcp") as mock_mcp:
            result = runner.invoke(main, ["wrap", "omp", "--prepare-only"])
    assert result.exit_code == 0, result.output
    mock_mcp.assert_called_once()

def test_wrap_omp_custom_port(runner: CliRunner) -> None:
    """`--port N` is accepted and passed through."""
    with patch("headroom.cli.wrap.shutil.which", return_value="/usr/bin/omp"):
        with patch("headroom.cli.wrap._setup_headroom_mcp"):
            result = runner.invoke(main, ["wrap", "omp", "--prepare-only", "--port", "9090"])
    assert result.exit_code == 0, result.output
# ---------------------------------------------------------------------------
# Unwrap omp
# ---------------------------------------------------------------------------


def test_unwrap_omp_noop_when_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Unwrap is a safe no-op when the config file doesn't exist."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(main, ["unwrap", "omp"])
    assert result.exit_code == 0, result.output


def test_unwrap_omp_noop_when_no_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Unwrap is a safe no-op when the config has no Headroom markers."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    models_yml = tmp_path / "models.yml"
    models_yml.write_text("providers:\n  deepseek:\n    models: [\"deepseek-v4-flash\"]\n    baseUrl: https://original.example.com\n")
    result = runner.invoke(main, ["unwrap", "omp"])
    assert result.exit_code == 0, result.output
    assert "https://original.example.com" in models_yml.read_text()


def test_unwrap_omp_strips_config_yml_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Unwrap strips Headroom markers from .omp/config.yml."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    from headroom.providers.omp.config import (
        _CONFIG_MARKER_END,
        _CONFIG_MARKER_START,
    )
    config_yml = tmp_path / ".omp" / "config.yml"
    config_yml.parent.mkdir(parents=True)
    config_yml.write_text(
        "some_config: true\n"
        f"{_CONFIG_MARKER_START}\n"
        "  headroom:\n"
        "    proxy:\n"
        "      enabled: true\n"
        f"{_CONFIG_MARKER_END}\n"
    )
    result = runner.invoke(main, ["unwrap", "omp"])
    assert result.exit_code == 0, result.output
    content = config_yml.read_text()
    assert _CONFIG_MARKER_START not in content
    assert _CONFIG_MARKER_END not in content
    assert "some_config: true" in content

def test_unwrap_omp_config_noop_when_no_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
) -> None:
    """Unwrap is noop when config.yml has no Headroom markers."""
    _set_test_home(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    config_yml = tmp_path / ".omp" / "config.yml"
    config_yml.parent.mkdir(parents=True)
    config_yml.write_text("some_config: true\n")
    result = runner.invoke(main, ["unwrap", "omp"])
    assert result.exit_code == 0, result.output
    assert config_yml.read_text() == "some_config: true\n"

