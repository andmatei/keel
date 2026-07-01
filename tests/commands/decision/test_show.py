"""Tests for `keel decision show`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_show_renders_decision(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing"])
    assert result.exit_code == 0
    assert "Pick a thing" in result.stdout


def test_show_raw_dumps_file_unchanged(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing", "--raw"])
    assert result.exit_code == 0
    assert "title: Pick a thing" in result.stdout
    assert "## Question" in result.stdout


def test_show_json(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    result = runner.invoke(app, ["decision", "show", "pick-a-thing", "--json"])
    payload = json.loads(result.stdout)
    assert payload["frontmatter"]["title"] == "Pick a thing"
    assert "## Question" in payload["body_markdown"]


def test_show_unknown_slug(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["decision", "show", "nonexistent"])
    assert result.exit_code == 1


def test_show_rejects_path_slug(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["decision", "show", "../scope.md"])
    assert result.exit_code == 1


def test_show_unknown_slug_includes_hint(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["decision", "show", "nonexistent"])
    assert result.exit_code == 1
    assert "Hint" in result.stderr
    assert "keel decision list" in result.stderr
