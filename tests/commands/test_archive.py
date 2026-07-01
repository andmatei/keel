"""Tests for `keel archive`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_archive_moves_project_to_archive(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["archive", "foo", "-y"])
    assert result.exit_code == 0
    assert not (projects / "foo").exists()
    archive_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archive_dirs) == 1
    assert (archive_dirs[0] / ".archived").is_file()
    assert (archive_dirs[0] / "project.toml").is_file()


def test_archive_unknown(projects) -> None:
    result = runner.invoke(app, ["archive", "ghost", "-y"])
    assert result.exit_code == 1


def test_archive_dry_run(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["archive", "foo", "-y", "--dry-run"])
    assert result.exit_code == 0
    assert (projects / "foo").exists()
    assert not (projects / ".archive").exists()


def test_archive_with_worktree_clean(projects, make_project, source_repo) -> None:
    """Archive correctly removes a clean worktree before moving the project."""
    from keel import git_ops

    proj = make_project("foo")
    git_ops.create_worktree(source_repo, proj / "code", branch="alice/foo")
    result = runner.invoke(app, ["archive", "foo", "-y"])
    assert result.exit_code == 0
    archive_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archive_dirs) == 1
    # Worktree was removed before move (so it's not in the archive):
    assert not (archive_dirs[0] / "code").exists()


def test_archive_fires_pre_and_post(projects, make_project, monkeypatch) -> None:
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.builtin_listeners import register_builtin_listeners
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    register_builtin_listeners()
    try:
        fired: list[str] = []
        archived_paths: list[str] = []

        @subscribes_to("project.archive.pre")
        def pre(event: HookEvent, *, out) -> None:
            fired.append(event.full_name)
            assert event.project == "foo"

        @subscribes_to("project.archive.post")
        def post(event: HookEvent, *, out) -> None:
            fired.append(event.full_name)
            archived_paths.append(event.payload["archived_path"])

        runner = CliRunner()
        make_project("foo")
        monkeypatch.chdir(projects)
        result = runner.invoke(app, ["archive", "foo", "-y"])
        assert result.exit_code == 0, result.stderr
        assert fired == ["project.archive.pre", "project.archive.post"]
        assert len(archived_paths) == 1
        assert "foo-" in archived_paths[0]
    finally:
        _clear_registry()
        register_builtin_listeners()
