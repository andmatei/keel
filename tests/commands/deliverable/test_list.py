"""Tests for `keel deliverable list`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_list_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo"])
    assert result.exit_code == 0
    # Empty output or "(no deliverables)" — accept either.
    assert "no deliverables" in result.stdout.lower() or result.stdout.strip() == ""


def test_list_one_deliverable(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="the bar")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo"])
    assert result.exit_code == 0
    assert "bar" in result.stdout


def test_list_json_shape(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="the bar")
    result = runner.invoke(app, ["deliverable", "list", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert "deliverables" in payload
    assert payload["deliverables"][0]["name"] == "bar"
    assert payload["deliverables"][0]["phase"] == "scoping"
    assert payload["deliverables"][0]["description"] == "the bar"


def test_list_auto_detects_project_from_cwd(
    projects, make_project, make_deliverable, monkeypatch
) -> None:
    proj = make_deliverable(project_name="foo", name="bar", description="d").parent.parent
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["deliverable", "list"])
    assert result.exit_code == 0
    assert "bar" in result.stdout


def test_list_tag_filter(projects, make_deliverable) -> None:
    from keel import workspace
    from keel.manifest import load_project_manifest, save_project_manifest

    make_deliverable(project_name="foo", name="alpha", description="a")
    make_deliverable(project_name="foo", name="beta", description="b")
    d_a = workspace.deliverable_dir("foo", "alpha")
    d_b = workspace.deliverable_dir("foo", "beta")
    m_a = load_project_manifest(d_a / "project.toml")
    m_a.project.tags = ["api"]
    save_project_manifest(d_a / "project.toml", m_a)
    m_b = load_project_manifest(d_b / "project.toml")
    m_b.project.tags = ["webhook"]
    save_project_manifest(d_b / "project.toml", m_b)

    result = runner.invoke(
        app, ["deliverable", "list", "--project", "foo", "--tag", "api", "--json"]
    )
    payload = json.loads(result.stdout)
    assert len(payload["deliverables"]) == 1
    assert payload["deliverables"][0]["name"] == "alpha"


def test_list_shows_tags_in_json(projects, make_deliverable) -> None:
    from keel import workspace
    from keel.manifest import load_project_manifest, save_project_manifest

    make_deliverable(project_name="foo", name="bar")
    d = workspace.deliverable_dir("foo", "bar")
    m = load_project_manifest(d / "project.toml")
    m.project.tags = ["api", "webhook"]
    save_project_manifest(d / "project.toml", m)

    result = runner.invoke(app, ["deliverable", "list", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["deliverables"][0]["tags"] == ["api", "webhook"]
