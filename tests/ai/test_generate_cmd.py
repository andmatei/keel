"""Tests for `keel ai generate`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_generate_stdout(projects, make_project, monkeypatch) -> None:
    make_project("foo")
    monkeypatch.chdir(projects / "foo")
    result = runner.invoke(app, ["ai", "generate"])
    assert result.exit_code == 0, result.stderr
    assert "# Project: foo" in result.stdout


def test_generate_json(projects, make_project, monkeypatch) -> None:
    make_project("foo")
    monkeypatch.chdir(projects / "foo")
    result = runner.invoke(app, ["ai", "generate", "--json"])
    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)
    assert "content" in data
    assert "# Project: foo" in data["content"]


def test_generate_output_dir(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["ai", "generate", "--output", str(proj)])
    assert result.exit_code == 0, result.stderr
    assert (proj / "AGENTS.md").is_file()
    assert "# Project: foo" in (proj / "AGENTS.md").read_text()
    assert (proj / "CLAUDE.md").is_file()
    assert "AGENTS.md" in (proj / "CLAUDE.md").read_text()


def test_generate_json_with_output(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(
        app, ["ai", "generate", "--json", "--output", str(proj)]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["path"] == str(proj)
    assert "content" in data


def test_generate_no_project_fails(projects, monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ai", "generate"])
    assert result.exit_code != 0
