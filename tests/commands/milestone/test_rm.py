"""Tests for `keel milestone rm`."""

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_milestones_manifest

runner = CliRunner()


def test_rm_cancelled_milestone(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "T"])
    runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    result = runner.invoke(app, ["milestone", "rm", "m1", "-y"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones == []


def test_rm_active_milestone_blocked_without_force(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "T"])
    runner.invoke(app, ["milestone", "start", "m1"])
    result = runner.invoke(app, ["milestone", "rm", "m1", "-y"])
    assert result.exit_code == 1


def test_rm_with_force(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "T"])
    runner.invoke(app, ["milestone", "start", "m1"])
    result = runner.invoke(app, ["milestone", "rm", "m1", "-y", "--force"])
    assert result.exit_code == 0


def test_rm_force_moves_referencing_tasks_to_default(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "T"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "Task"])

    result = runner.invoke(app, ["milestone", "rm", "m1", "-y", "--force"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml", validate=True)
    assert [task.milestone for task in m.tasks] == ["default"]


def test_rm_unknown_id(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["milestone", "rm", "nonexistent", "-y"])
    assert result.exit_code == 1


def test_rm_dry_run_writes_nothing(projects, make_project, monkeypatch) -> None:
    """Dry-run validates but does not delete the milestone."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "T"])
    runner.invoke(app, ["milestone", "cancel", "m1", "-y"])

    # Capture pre-state
    mp = proj / "milestones.toml"
    pre_text = mp.read_text()

    result = runner.invoke(app, ["milestone", "rm", "m1", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0
    # Confirm milestone still exists
    post_text = mp.read_text()
    assert pre_text == post_text
    m = load_milestones_manifest(mp)
    assert any(mile.id == "m1" for mile in m.milestones)
