"""Tests for `keel tag add`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_project_manifest

runner = CliRunner()


def test_tag_add_one(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "add", "api", "--project", "foo"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == ["api"]


def test_tag_add_multiple(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "add", "api", "webhook", "--project", "foo"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert set(m.project.tags) == {"api", "webhook"}


def test_tag_add_idempotent(projects, make_project) -> None:
    make_project("foo")
    runner.invoke(app, ["tag", "add", "api", "--project", "foo"])
    result = runner.invoke(app, ["tag", "add", "api", "--project", "foo"])
    assert result.exit_code == 0
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == ["api"]


def test_tag_add_invalid_rejected(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "add", "bad tag!", "--project", "foo"])
    assert result.exit_code != 0


def test_tag_add_json(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["tag", "add", "api", "--project", "foo", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "api" in payload["tags"]


def test_tag_add_auto_detect_scope(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["tag", "add", "api"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == ["api"]


def test_tag_add_on_deliverable(projects, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar")
    result = runner.invoke(app, ["tag", "add", "api", "--project", "foo", "--deliverable", "bar"])
    assert result.exit_code == 0, result.stderr
    from keel import workspace

    deliv_path = workspace.deliverable_dir("foo", "bar") / "project.toml"
    m = load_project_manifest(deliv_path)
    assert m.project.tags == ["api"]
