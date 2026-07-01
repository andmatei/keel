"""Tests for `keel tag list`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_project_manifest, save_project_manifest

runner = CliRunner()


def _add_tags(unit_dir, tags: list[str]) -> None:
    m = load_project_manifest(unit_dir / "project.toml")
    m.project.tags = tags
    save_project_manifest(unit_dir / "project.toml", m)


def test_tag_list_scoped(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "list", "--project", "foo"])
    assert result.exit_code == 0
    assert "api" in result.stdout
    assert "webhook" in result.stdout


def test_tag_list_scoped_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "list", "--project", "foo"])
    assert result.exit_code == 0
    assert "no tags" in result.stdout.lower()


def test_tag_list_scoped_json(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "list", "--project", "foo", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["tags"]) == {"api", "webhook"}


def test_tag_list_global(projects, make_project) -> None:
    proj_a = make_project("alpha")
    proj_b = make_project("beta")
    _add_tags(proj_a, ["api", "research"])
    _add_tags(proj_b, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0
    assert "api" in result.stdout
    assert "alpha" in result.stdout
    assert "beta" in result.stdout


def test_tag_list_global_json(projects, make_project) -> None:
    proj_a = make_project("alpha")
    proj_b = make_project("beta")
    _add_tags(proj_a, ["api"])
    _add_tags(proj_b, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "api" in payload["tags"]
    assert set(payload["tags"]["api"]["projects"]) == {"alpha", "beta"}
    assert payload["tags"]["webhook"]["projects"] == ["beta"]


def test_tag_list_global_includes_deliverables(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar")
    from keel import workspace

    deliv_dir = workspace.deliverable_dir("foo", "bar")
    _add_tags(deliv_dir, ["api"])
    result = runner.invoke(app, ["tag", "list", "--json"])
    payload = json.loads(result.stdout)
    assert "api" in payload["tags"]
    assert len(payload["tags"]["api"]["deliverables"]) == 1
    assert payload["tags"]["api"]["deliverables"][0]["name"] == "bar"


def test_tag_list_global_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0
    assert "no tags" in result.stdout.lower()


def test_tag_list_auto_detect_scope(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api"])
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["tag", "list"])
    assert result.exit_code == 0
    assert "api" in result.stdout
