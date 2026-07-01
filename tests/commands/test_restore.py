"""Tests for `keel restore`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_restore_basic(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj.parent)
    runner.invoke(app, ["archive", "foo", "-y"])
    assert not proj.exists()
    # Archive creates foo-YYYY-MM-DD
    archived_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archived_dirs) == 1

    result = runner.invoke(app, ["restore", "foo", "-y"])
    assert result.exit_code == 0
    assert proj.is_dir()
    # The archived directory should be gone
    archived_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archived_dirs) == 0


def test_restore_unknown_fails(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    result = runner.invoke(app, ["restore", "nonexistent", "-y"])
    assert result.exit_code == 1


def test_restore_with_existing_target_fails(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj.parent)
    runner.invoke(app, ["archive", "foo", "-y"])
    # Now create a NEW foo project that conflicts
    make_project("foo")
    result = runner.invoke(app, ["restore", "foo", "-y"])
    assert result.exit_code == 1


def test_restore_dry_run(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj.parent)
    runner.invoke(app, ["archive", "foo", "-y"])
    archived_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archived_dirs) == 1
    result = runner.invoke(app, ["restore", "foo", "-y", "--dry-run"])
    assert result.exit_code == 0
    # Still archived after dry run
    archived_dirs = list((projects / ".archive").glob("foo-*"))
    assert len(archived_dirs) == 1


def test_restore_fires_post_restore(projects, monkeypatch) -> None:
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.builtin_listeners import register_builtin_listeners
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    register_builtin_listeners()
    try:
        fired: list[str] = []

        @subscribes_to("project.restore.post")
        def post(event: HookEvent, *, out) -> None:
            fired.append(event.full_name)
            assert event.project == "foo"
            assert "path" in event.payload

        # Set up an archived project
        runner = CliRunner()
        monkeypatch.chdir(projects)
        (projects / ".archive").mkdir()
        archived = projects / ".archive" / "foo-2025-01-01"
        archived.mkdir()
        (archived / ".archived").write_text("archived: 2025-01-01\nfrom: /old\n")

        result = runner.invoke(app, ["restore", "foo", "-y"])
        assert result.exit_code == 0, result.stderr
        assert fired == ["project.restore.post"]
    finally:
        _clear_registry()
        register_builtin_listeners()
