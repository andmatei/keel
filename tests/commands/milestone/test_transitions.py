"""Tests for `keel milestone start/done/cancel`."""

import pytest
from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_milestones_manifest

runner = CliRunner()


def _add(proj_dir):
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Foundation"])


def test_start_planned_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    result = runner.invoke(app, ["milestone", "start", "m1"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones[0].status == "active"


def test_start_rejects_wrong_state(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    runner.invoke(app, ["milestone", "start", "m1"])  # planned -> active
    result = runner.invoke(app, ["milestone", "start", "m1"])  # already active
    assert result.exit_code == 1


def test_start_reopen_done_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    runner.invoke(app, ["milestone", "start", "m1"])
    runner.invoke(app, ["milestone", "done", "m1"])
    # Without --reopen, start fails
    result = runner.invoke(app, ["milestone", "start", "m1"])
    assert result.exit_code == 1
    # With --reopen, start succeeds
    result = runner.invoke(app, ["milestone", "start", "m1", "--reopen"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones[0].status == "active"


def test_start_reopen_cancelled_to_active(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    result = runner.invoke(app, ["milestone", "start", "m1"])
    assert result.exit_code == 1
    result = runner.invoke(app, ["milestone", "start", "m1", "--reopen"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones[0].status == "active"


def test_done_active_to_done(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    runner.invoke(app, ["milestone", "start", "m1"])
    result = runner.invoke(app, ["milestone", "done", "m1"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones[0].status == "done"


def test_done_idempotent(projects, make_project, monkeypatch) -> None:
    """Marking an already-done milestone as done is a no-op."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    runner.invoke(app, ["milestone", "start", "m1"])
    runner.invoke(app, ["milestone", "done", "m1"])
    result = runner.invoke(app, ["milestone", "done", "m1"])
    assert result.exit_code == 0


def test_done_rejects_wrong_state(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add(proj)
    # Still planned, not active
    result = runner.invoke(app, ["milestone", "done", "m1"])
    assert result.exit_code == 1


def test_done_blocks_when_own_tasks_active(projects, make_project, monkeypatch) -> None:
    """Done on a milestone blocks if it has active tasks."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T1"])
    runner.invoke(app, ["milestone", "start", "m1"])
    runner.invoke(app, ["task", "start", "t1"])

    result = runner.invoke(app, ["milestone", "done", "m1"])
    assert result.exit_code == 1
    assert "tasks not complete" in result.stdout.lower() or "tasks not complete" in (
        result.stderr or ""
    ).lower()

    # With --force, succeeds
    result = runner.invoke(app, ["milestone", "done", "m1", "--force"])
    assert result.exit_code == 0


def test_done_blocks_when_own_tasks_planned(projects, make_project, monkeypatch) -> None:
    """Done on a milestone blocks if it has planned (not-yet-started) tasks."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T1"])
    runner.invoke(app, ["milestone", "start", "m1"])
    # t1 is still planned

    result = runner.invoke(app, ["milestone", "done", "m1"])
    assert result.exit_code == 1

    result = runner.invoke(app, ["milestone", "done", "m1", "--force"])
    assert result.exit_code == 0


def test_done_allows_cancelled_tasks(projects, make_project, monkeypatch) -> None:
    """A milestone can be marked done if all its tasks are done or cancelled."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T1"])
    runner.invoke(app, ["milestone", "start", "m1"])
    runner.invoke(app, ["task", "cancel", "t1", "-y"])

    result = runner.invoke(app, ["milestone", "done", "m1"])
    assert result.exit_code == 0


def test_done_blocks_when_sub_milestones_not_done(
    projects, make_project, make_deliverable, monkeypatch
) -> None:
    """Done on a project milestone blocks if a deliverable has a sub-milestone with parent pointing back."""
    from keel.manifest import Milestone, MilestonesManifest, save_milestones_manifest
    from keel.workspace import Scope

    proj = make_project("foo")
    make_deliverable(project_name="foo", name="alpha", description="d")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Big", "--project", "foo"])

    # Create a sub-milestone in the deliverable pointing back to m1
    sub_scope = Scope(project="foo", deliverable="alpha")
    save_milestones_manifest(
        sub_scope.milestones_manifest_path,
        MilestonesManifest(
            milestones=[Milestone(id="sub-m1", title="Alpha work", parent="m1", status="active")]
        ),
    )

    runner.invoke(app, ["milestone", "start", "m1", "--project", "foo"])
    # Sub-milestone not done → done should fail without --force
    result = runner.invoke(app, ["milestone", "done", "m1", "--project", "foo"])
    assert result.exit_code == 1

    # With --force, succeeds
    result = runner.invoke(app, ["milestone", "done", "m1", "--project", "foo", "--force"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "setup_actions,expected_initial",
    [
        ([], "planned"),
        ([("milestone", "start", "m1")], "active"),
    ],
    ids=["from_planned", "from_active"],
)
def test_cancel_from_state(
    projects, make_project, monkeypatch, setup_actions, expected_initial
) -> None:
    """Cancel works from planned and active states."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "x"])
    for cmd in setup_actions:
        runner.invoke(app, list(cmd))
    m_state = load_milestones_manifest(proj / "milestones.toml")
    assert m_state.milestones[0].status == expected_initial
    result = runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    assert result.exit_code == 0
    m_after = load_milestones_manifest(proj / "milestones.toml")
    assert m_after.milestones[0].status == "cancelled"


def test_cancel_done_requires_force(projects, make_project, monkeypatch) -> None:
    """Cancelling a done milestone requires --force."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "x"])
    runner.invoke(app, ["milestone", "start", "m1"])
    runner.invoke(app, ["milestone", "done", "m1"])

    result = runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    assert result.exit_code == 1

    result = runner.invoke(app, ["milestone", "cancel", "m1", "-y", "--force"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones[0].status == "cancelled"


def test_cancel_idempotent(projects, make_project, monkeypatch) -> None:
    """Cancelling an already-cancelled milestone is a no-op."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "x"])
    runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    result = runner.invoke(app, ["milestone", "cancel", "m1", "-y"])
    assert result.exit_code == 0


def test_done_dry_run_writes_nothing(projects, make_project, monkeypatch) -> None:
    """Dry-run validates but does not mark milestone as done."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "Foundation"])
    runner.invoke(app, ["milestone", "start", "m1"])

    # Capture pre-state
    mp = proj / "milestones.toml"
    pre_text = mp.read_text()

    result = runner.invoke(app, ["milestone", "done", "m1", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0
    # Confirm status unchanged
    post_text = mp.read_text()
    assert pre_text == post_text
    m = load_milestones_manifest(mp)
    assert m.milestones[0].status == "active"
