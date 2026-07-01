"""Tests for `keel milestone show`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_show_basic(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Foundation"])
    result = runner.invoke(app, ["milestone", "show", "m1"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "m1" in result.stdout
    assert "Foundation" in result.stdout
    assert "planned" in result.stdout


def test_show_json(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Foundation"])
    result = runner.invoke(app, ["milestone", "show", "m1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "m1"
    assert data["title"] == "Foundation"
    assert data["status"] == "planned"
    assert "task_count" in data
    assert data["task_count"] == 0
    assert data["tickets"] == {}
    assert data["description"] is None


def test_show_unknown_id_fails(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["milestone", "show", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower() or "no milestone" in result.stderr.lower()
