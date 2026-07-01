"""Tests for `keel ai show-config`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app
from keel.api import load_project_manifest, save_project_manifest

runner = CliRunner()


def test_show_config_no_ai_section(projects, make_project, monkeypatch) -> None:
    """Without [extensions.ai], returns defaults + resolved lifecycle triggers."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "show-config", "--json"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["enabled"] is True
    assert data["triggers"] == {}
    assert data["lifecycle"] == "default"
    assert "task_done_sync" in data["resolved_triggers"]
    assert "task_done_review" in data["resolved_triggers"]


def test_show_config_with_triggers(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {
        "enabled": True,
        "triggers": {
            "task_done": {
                "event": "task.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "lightweight",
            }
        },
    }
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "show-config", "--json"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["triggers"]["task_done"]["mode"] == "lightweight"


def test_show_config_disabled(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"enabled": False}
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "show-config", "--json"])
    data = json.loads(result.stdout)
    assert data["enabled"] is False


def test_show_config_invalid_rejects(projects, make_project, monkeypatch) -> None:
    """Bad config should fail with a validation error."""
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"triggers": {"bad": {"event": "x.y"}}}  # missing 'action'
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "show-config", "--json"])
    assert result.exit_code != 0


def test_show_config_human_output(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "show-config"])
    assert result.exit_code == 0
    assert "enabled" in result.stdout.lower()
    assert "Effective triggers:" in result.stdout
    assert "(default)" in result.stdout
