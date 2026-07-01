"""Tests for `keel decision rm`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_rm_removes_decision_file(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["decision", "new", "Pick a thing", "--no-edit"])
    decisions = list((proj / "decisions").glob("*-pick-a-thing.md"))
    assert len(decisions) == 1
    runner.invoke(app, ["decision", "rm", "pick-a-thing", "-y"])
    decisions_after = list((proj / "decisions").glob("*-pick-a-thing.md"))
    assert decisions_after == []


def test_rm_unknown(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["decision", "rm", "nonexistent", "-y"])
    assert result.exit_code == 1


def test_rm_rejects_path_slug(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["decision", "rm", "../scope.md", "-y"])
    assert result.exit_code == 1
    assert (proj / "scope.md").is_file()
