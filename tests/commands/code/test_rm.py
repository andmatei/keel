"""Tests for `keel code rm`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_rm_removes_manifest_entry_and_worktree(projects, make_project, source_repo) -> None:
    make_project("foo")
    add_result = runner.invoke(
        app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert add_result.exit_code == 0, add_result.stderr
    from keel.manifest import load_project_manifest

    m = load_project_manifest(projects / "foo" / "project.toml")
    wt_path = projects / "foo" / m.repos[0].worktree
    assert wt_path.is_dir()

    result = runner.invoke(
        app, ["code", "rm", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert result.exit_code == 0
    assert not wt_path.exists()
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.repos == []


def test_rm_unknown_repo(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(
        app, ["code", "rm", "--project", "foo", "--repo", "git@e.com:o/x.git", "-y"]
    )
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower() or "no repo" in result.stderr.lower()


def test_rm_dirty_worktree_without_force(projects, make_project, source_repo) -> None:
    make_project("foo")
    add_result = runner.invoke(
        app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert add_result.exit_code == 0, add_result.stderr
    from keel.manifest import load_project_manifest

    m = load_project_manifest(projects / "foo" / "project.toml")
    wt_path = projects / "foo" / m.repos[0].worktree
    (wt_path / "dirty.txt").write_text("dirty")
    result = runner.invoke(
        app, ["code", "rm", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert result.exit_code == 1


def test_rm_preserves_manifest_extensions(projects, make_project, source_repo) -> None:
    proj = make_project("foo")
    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo)])
    from keel.manifest import load_project_manifest, save_project_manifest

    m = load_project_manifest(proj / "project.toml")
    m.extensions = {"ticketing": {"provider": "mock"}}
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(
        app, ["code", "rm", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(proj / "project.toml")
    assert m.extensions == {"ticketing": {"provider": "mock"}}
