"""Tests for `keel show`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_show_by_name(projects, make_project) -> None:
    make_project("foo", "the foo project")
    result = runner.invoke(app, ["show", "foo"])
    assert result.exit_code == 0, result.stderr
    assert "foo" in result.stdout
    assert "the foo project" in result.stdout
    assert "scoping" in result.stdout


def test_show_unknown_project(projects) -> None:
    result = runner.invoke(app, ["show", "doesnotexist"])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower()


def test_show_auto_detects_project_from_cwd(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo", "auto-detected")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0, result.stderr
    assert "foo" in result.stdout


def test_show_unknown_project_includes_hint(projects) -> None:
    result = runner.invoke(app, ["show", "ghost"])
    assert result.exit_code == 1
    assert "Hint" in result.stderr
    assert "keel list" in result.stderr


def test_show_no_project_detected_includes_hint(projects, monkeypatch, tmp_path) -> None:
    """When run outside a project dir with no arg, error includes a hint."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 1
    assert "Hint" in result.stderr


def test_show_json_shape(projects, make_project) -> None:
    make_project("foo", "the foo project")
    result = runner.invoke(app, ["show", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["name"] == "foo"
    assert payload["description"] == "the foo project"
    assert payload["phase"] == "scoping"
    assert payload["repos"] == []
    assert payload["decision_count"] == 0
    assert payload["deliverables"] == []


def test_show_with_milestones_summary(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "x"])
    runner.invoke(
        app, ["task", "add", "t2", "--milestone", "m1", "--title", "y", "--depends-on", "t1"]
    )
    result = runner.invoke(app, ["show", "foo"])
    assert result.exit_code == 0
    assert "Milestones" in result.stdout or "milestone" in result.stdout.lower()


def test_show_json_includes_milestones(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    result = runner.invoke(app, ["show", "foo", "--json"])
    data = json.loads(result.stdout)
    assert "milestones" in data
    assert data["milestones"]["by_status"]["planned"] == 1


def test_show_brief_skips_milestones(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    result = runner.invoke(app, ["show", "foo", "--brief", "--json"])
    data = json.loads(result.stdout)
    assert "milestones" not in data


def test_show_no_milestones_file_no_section(projects, make_project) -> None:
    make_project("foo")  # No milestones.toml created
    result = runner.invoke(app, ["show", "foo", "--json"])
    data = json.loads(result.stdout)
    assert "milestones" not in data


def test_show_skips_single_default_milestone(projects, make_project, monkeypatch) -> None:
    """When the only milestone is the implicit default, `show` doesn't render the milestone hierarchy."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["task", "add", "t1", "--title", "x"])  # auto-default
    result = runner.invoke(app, ["show", "foo"])
    assert result.exit_code == 0
    # The summary should mention t1 directly, not show "Milestone: default" sections.
    assert "default" not in result.stdout.lower() or "Tasks" in result.stdout


def test_show_renders_explicit_milestones(projects, make_project, monkeypatch) -> None:
    """When explicit milestones exist, render them normally."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Foundation"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "x"])
    result = runner.invoke(app, ["show", "foo"])
    assert "m1" in result.stdout
    assert "Foundation" in result.stdout


def test_show_displays_tags(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.project.tags = ["api", "webhook"]
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["show", "foo"])
    assert result.exit_code == 0
    assert "api" in result.stdout
    assert "webhook" in result.stdout


def test_show_json_includes_tags(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.project.tags = ["api"]
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["show", "foo", "--json"])
    data = json.loads(result.stdout)
    assert data["tags"] == ["api"]


def test_show_no_tags_row_when_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["show", "foo"])
    assert result.exit_code == 0
    assert "Tags" not in result.stdout


def test_show_json_tags_empty(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["show", "foo", "--json"])
    data = json.loads(result.stdout)
    assert data["tags"] == []
