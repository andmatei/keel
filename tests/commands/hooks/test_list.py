"""Tests for `keel hooks list`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app


def test_hooks_list_default_shows_events(projects, monkeypatch) -> None:
    """Default `keel hooks list` shows known event names."""
    runner = CliRunner()
    monkeypatch.chdir(projects)
    result = runner.invoke(app, ["hooks", "list"])
    assert result.exit_code == 0, result.stderr
    # Should mention some known events
    assert "project.create" in result.stdout
    assert "project.phase" in result.stdout


def test_hooks_list_json(projects, monkeypatch) -> None:
    """JSON mode produces a structured payload."""
    runner = CliRunner()
    monkeypatch.chdir(projects)
    result = runner.invoke(app, ["hooks", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "events" in payload
    assert "project.create" in payload["events"]


def test_hooks_list_shows_in_tree_subscribers(projects, monkeypatch) -> None:
    """In-tree subscribers (e.g. built-in pre-phase listeners) are visible."""
    runner = CliRunner()
    monkeypatch.chdir(projects)
    result = runner.invoke(app, ["hooks", "list", "--json"])
    payload = json.loads(result.stdout)
    phase = payload["events"].get("project.phase", {})
    pre_subs = phase.get("pre_subscribers", [])
    # Built-in listeners include _check_scope_md_edited etc.
    assert any("scope_md_edited" in s for s in pre_subs)
