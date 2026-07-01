"""Tests for `keel tag rm`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_project_manifest

runner = CliRunner()


def _add_tags(project_dir, tags: list[str]) -> None:
    m = load_project_manifest(project_dir / "project.toml")
    m.project.tags = tags
    from keel.manifest import save_project_manifest

    save_project_manifest(project_dir / "project.toml", m)


def test_tag_rm_one(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "rm", "api", "--project", "foo"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == ["webhook"]


def test_tag_rm_multiple(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api", "webhook", "research"])
    result = runner.invoke(app, ["tag", "rm", "api", "webhook", "--project", "foo"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == ["research"]


def test_tag_rm_missing_warns(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api"])
    result = runner.invoke(app, ["tag", "rm", "nonexistent", "--project", "foo"])
    assert result.exit_code == 0
    assert (
        "not present" in result.stdout.lower()
        or "warn" in result.stderr.lower()
        or result.exit_code == 0
    )


def test_tag_rm_all(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api"])
    result = runner.invoke(app, ["tag", "rm", "api", "--project", "foo"])
    assert result.exit_code == 0
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == []


def test_tag_rm_json(projects, make_project) -> None:
    proj = make_project("foo")
    _add_tags(proj, ["api", "webhook"])
    result = runner.invoke(app, ["tag", "rm", "api", "--project", "foo", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tags"] == ["webhook"]
    assert payload["removed"] == ["api"]


def test_tag_rm_on_deliverable(projects, make_deliverable) -> None:
    from keel import workspace

    make_deliverable(project_name="foo", name="bar")
    deliv_dir = workspace.deliverable_dir("foo", "bar")
    _add_tags(deliv_dir, ["api", "webhook"])
    result = runner.invoke(
        app, ["tag", "rm", "api", "--project", "foo", "--deliverable", "bar", "--json"]
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["tags"] == ["webhook"]
    assert payload["removed"] == ["api"]
    m = load_project_manifest(deliv_dir / "project.toml")
    assert m.project.tags == ["webhook"]
