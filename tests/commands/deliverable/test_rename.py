"""Tests for `keel deliverable rename`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_rename_moves_design_dir(projects, make_project, make_deliverable) -> None:
    old = make_deliverable(project_name="foo", name="bar", description="d")
    result = runner.invoke(
        app,
        ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert not old.exists()
    new = projects / "foo" / "deliverables" / "baz"
    assert new.is_dir()
    assert (new / "project.toml").is_file()


def test_rename_updates_manifest_name(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="d")
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    from keel.manifest import load_project_manifest

    m = load_project_manifest(projects / "foo" / "deliverables" / "baz" / "project.toml")
    assert m.project.name == "baz"


def test_rename_preserves_manifest_metadata(projects, make_deliverable) -> None:
    deliv = make_deliverable(project_name="foo", name="bar", description="d", tags=["api"])
    from keel.manifest import load_project_manifest, save_project_manifest

    m = load_project_manifest(deliv / "project.toml")
    m.extensions = {"ai": {"enabled": False}}
    save_project_manifest(deliv / "project.toml", m)

    result = runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "deliverables" / "baz" / "project.toml")
    assert m.project.tags == ["api"]
    assert m.extensions == {"ai": {"enabled": False}}


def test_rename_fails_if_target_exists(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="bar", description="d")
    make_deliverable(project_name="foo", name="baz", description="d")
    result = runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    assert result.exit_code == 1
    assert "exists" in result.stderr.lower()


def test_rename_updates_parent_references(projects, make_project) -> None:
    """After rename, the parent's design.md mentions the new name and not the old."""
    make_project("foo")
    runner.invoke(app, ["deliverable", "add", "bar", "-d", "d", "-y", "--project", "foo"])
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    parent_design = (projects / "foo" / "design.md").read_text()
    assert "**bar**" not in parent_design
    assert "**baz**" in parent_design


def test_rename_uses_git_worktree_move_when_code_present(
    projects, make_project, make_deliverable, monkeypatch, tmp_path
) -> None:
    """When deliv/code/ exists, rename calls git.move_worktree, not shutil.move on it."""
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    (deliv / "code").mkdir()
    (deliv / "code" / "x.txt").write_text("data")
    move_calls = []

    def fake_move_worktree(old_dest, new_dest):
        # Simulate git's move: move the directory contents.
        import shutil

        shutil.move(str(old_dest), str(new_dest))
        move_calls.append((str(old_dest), str(new_dest)))

    monkeypatch.setattr("keel.git.move_worktree", fake_move_worktree)
    # Avoid the rename_branch path's git ops (it'll run because branch_prefix is None on this fixture)
    # The fixture's manifest has repos=[] so branch rename is skipped naturally.
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
    new = projects / "foo" / "deliverables" / "baz"
    assert not deliv.exists()
    assert new.is_dir()
    assert (new / "code" / "x.txt").read_text() == "data"
    # git.move_worktree was called exactly once with the correct paths:
    assert move_calls == [(str(deliv / "code"), str(new / "code"))]


def test_rename_does_not_call_git_worktree_repair(
    projects, make_project, make_deliverable, monkeypatch
) -> None:
    """The old shutil.move + git worktree repair dance should be gone."""
    deliv = make_deliverable(project_name="foo", name="bar", description="d")
    (deliv / "code").mkdir()
    (deliv / "code" / "x.txt").write_text("x")
    monkeypatch.setattr("keel.git.move_worktree", lambda *a: None)
    # Fail loudly if `git worktree repair` is invoked via subprocess.run
    import subprocess

    real_run = subprocess.run

    def assert_no_repair(args, **kwargs):
        assert "repair" not in args, f"unexpected git worktree repair: {args}"
        return real_run(args, **kwargs)

    monkeypatch.setattr("subprocess.run", assert_no_repair)
    runner.invoke(app, ["deliverable", "rename", "bar", "baz", "-y", "--project", "foo"])
