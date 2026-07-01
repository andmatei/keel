"""Tests for `keel task start/done/cancel`."""

import pytest
from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_milestones_manifest

runner = CliRunner()


def _seed(proj, monkeypatch):
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "First"])


def test_start_planned_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    result = runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"
    assert m.tasks[0].branch is not None
    assert "m1" in m.tasks[0].branch
    assert "t1" in m.tasks[0].branch


def test_start_with_explicit_branch(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    result = runner.invoke(app, ["task", "start", "t1", "--branch", "custom/branch"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].branch == "custom/branch"


def test_start_rejects_wrong_state(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "start", "t1"])
    result = runner.invoke(app, ["task", "start", "t1"])  # already active
    assert result.exit_code == 1


def test_start_reopen_done_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "start", "t1"])
    runner.invoke(app, ["task", "done", "t1"])
    result = runner.invoke(app, ["task", "start", "t1"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["task", "start", "t1", "--reopen"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"


def test_start_reopen_cancelled_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "cancel", "t1", "-y"])
    result = runner.invoke(app, ["task", "start", "t1"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["task", "start", "t1", "--reopen"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"


def test_done_active_to_done(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "start", "t1"])
    result = runner.invoke(app, ["task", "done", "t1"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "done"


def test_done_rejects_wrong_state(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    result = runner.invoke(app, ["task", "done", "t1"])  # still planned
    assert result.exit_code == 1


@pytest.mark.parametrize(
    "setup_actions,expected_initial",
    [
        ([], "planned"),
        ([("task", "start", "t1")], "active"),
    ],
    ids=["from_planned", "from_active"],
)
def test_cancel_from_state(
    projects, make_project, monkeypatch, setup_actions, expected_initial
) -> None:
    """Cancel works from planned and active states."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    for cmd in setup_actions:
        runner.invoke(app, list(cmd))
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == expected_initial
    result = runner.invoke(app, ["task", "cancel", "t1", "-y"])
    assert result.exit_code == 0
    m_after = load_milestones_manifest(proj / "milestones.toml")
    assert m_after.tasks[0].status == "cancelled"


def test_cancel_done_requires_force(projects, make_project, monkeypatch) -> None:
    """Cancelling a done task requires --force."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "start", "t1"])
    runner.invoke(app, ["task", "done", "t1"])

    result = runner.invoke(app, ["task", "cancel", "t1", "-y"])
    assert result.exit_code == 1

    result = runner.invoke(app, ["task", "cancel", "t1", "-y", "--force"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "cancelled"


def test_cancel_idempotent(projects, make_project, monkeypatch) -> None:
    """Cancelling an already-cancelled task is a no-op."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "cancel", "t1", "-y"])
    result = runner.invoke(app, ["task", "cancel", "t1", "-y"])
    assert result.exit_code == 0


def test_done_planned_requires_force(projects, make_project, monkeypatch) -> None:
    """Marking a planned task done requires --force."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    result = runner.invoke(app, ["task", "done", "t1"])
    assert result.exit_code == 1
    assert "--force" in result.output

    result = runner.invoke(app, ["task", "done", "t1", "--force"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "done"


def test_done_idempotent(projects, make_project, monkeypatch) -> None:
    """Marking an already-done task as done is a no-op."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "start", "t1"])
    runner.invoke(app, ["task", "done", "t1"])
    result = runner.invoke(app, ["task", "done", "t1"])
    assert result.exit_code == 0


def test_done_cancelled_rejected(projects, make_project, monkeypatch) -> None:
    """A cancelled task cannot be marked done even with --force."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    runner.invoke(app, ["task", "cancel", "t1", "-y"])
    result = runner.invoke(app, ["task", "done", "t1", "--force"])
    assert result.exit_code == 1
