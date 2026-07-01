"""Tests for keel daemon CLI commands."""
from __future__ import annotations

from typer.testing import CliRunner

from keel_daemon.commands import app

runner = CliRunner()


def test_daemon_list_no_daemons() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "(no daemons registered)" in result.output


def test_daemon_list_json_no_daemons() -> None:
    import json

    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"daemons": []}


def test_daemon_status_unknown() -> None:
    result = runner.invoke(app, ["status", "nonexistent"])
    assert result.exit_code != 0
    assert "nonexistent" in result.output


def test_daemon_start_unknown() -> None:
    result = runner.invoke(app, ["start", "nonexistent"])
    assert result.exit_code != 0
    assert "nonexistent" in result.output
