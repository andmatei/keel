"""Tests for `keel task rm`."""

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_milestones_manifest

runner = CliRunner()


def _seed(proj, monkeypatch):
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "First"])
    runner.invoke(
        app, ["task", "add", "t2", "--milestone", "m1", "--title", "Second", "--depends-on", "t1"]
    )


def test_rm_leaf_task(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    # t2 has no dependents — safe to remove.
    result = runner.invoke(app, ["task", "rm", "t2", "-y"], catch_exceptions=False)
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml")
    ids = [t.id for t in m.tasks]
    assert ids == ["t1"]


def test_rm_with_dependents_blocked(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    # t1 has dependent t2; should be blocked.
    result = runner.invoke(app, ["task", "rm", "t1", "-y"])
    assert result.exit_code == 1
    assert "t2" in result.stderr  # mentions blocking task


def test_rm_force_overrides(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    result = runner.invoke(app, ["task", "rm", "t1", "-y", "--force"])
    assert result.exit_code == 0
    m = load_milestones_manifest(proj / "milestones.toml", validate=True)
    assert all("t1" not in t.depends_on for t in m.tasks)


def test_rm_unknown_id(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["task", "rm", "nothing", "-y"])
    assert result.exit_code == 1


def test_rm_dry_run_writes_nothing(projects, make_project, monkeypatch) -> None:
    """Dry-run validates but does not delete the task."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)

    # Capture pre-state
    mp = proj / "milestones.toml"
    pre_text = mp.read_text()

    result = runner.invoke(app, ["task", "rm", "t2", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0
    # Confirm task still exists
    post_text = mp.read_text()
    assert pre_text == post_text
    m = load_milestones_manifest(mp)
    assert any(t.id == "t2" for t in m.tasks)


def test_rm_emptying_default_removes_it(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["task", "add", "t1", "--title", "x"])  # creates default
    result = runner.invoke(app, ["task", "rm", "t1", "-y"])
    assert result.exit_code == 0
    from keel.api import load_milestones_manifest

    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.milestones == []
