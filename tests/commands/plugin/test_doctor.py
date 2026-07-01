"""Tests for keel plugin doctor command."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_doctor_clean_project(projects, make_project, monkeypatch) -> None:
    """Test plugin doctor on a clean project."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["plugin", "doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["findings"] == []


def test_doctor_flags_unknown_provider(projects, make_project, monkeypatch) -> None:
    """Test plugin doctor flags unknown ticketing provider."""
    from keel.api import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ticketing"] = {"provider": "ghost"}
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["plugin", "doctor", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.stdout)
    assert any("ghost" in f["message"] for f in data["findings"])


def test_doctor_valid_ai_config(projects, make_project, monkeypatch) -> None:
    """Valid [extensions.ai] config should not produce findings."""
    from keel.api import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {
        "triggers": {
            "task_done": {
                "event": "task.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "lightweight",
            }
        }
    }
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["plugin", "doctor", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert not any(f["area"] == "ai" for f in data["findings"])


def test_doctor_invalid_ai_config(projects, make_project, monkeypatch) -> None:
    """Bad [extensions.ai] should produce an error finding."""
    from keel.api import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"triggers": {"bad": {"event": "x.y"}}}  # missing action
    save_project_manifest(proj / "project.toml", pm)
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["plugin", "doctor", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.stdout)
    assert any(f["area"] == "ai" for f in data["findings"])
