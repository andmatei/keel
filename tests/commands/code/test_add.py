"""Tests for `keel code add`."""

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_add_appends_to_manifest_and_creates_worktree(projects, make_project, source_repo) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    from keel.manifest import load_project_manifest

    m = load_project_manifest(projects / "foo" / "project.toml")
    assert len(m.repos) == 1
    assert m.repos[0].remote == str(source_repo)
    # first repo → "code"; worktree must exist
    assert (projects / "foo" / m.repos[0].worktree).is_dir()


def test_add_rejects_duplicate_remote(projects, make_project, source_repo) -> None:
    make_project("foo")
    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"])
    result = runner.invoke(
        app, ["code", "add", "--project", "foo", "--repo", str(source_repo), "-y"]
    )
    assert result.exit_code == 1
    assert "duplicate" in result.stderr.lower() or "already" in result.stderr.lower()


def test_add_rejects_duplicate_worktree_name(projects, make_project, tmp_path) -> None:
    """Two repos with same Path.name (basename) must be detected before they collide."""
    import subprocess

    make_project("foo")

    def _make_repo(p):
        p.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=p, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=p, check=True)
        (p / "README").write_text("x")
        subprocess.run(["git", "add", "."], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=p, check=True, capture_output=True)

    a = tmp_path / "first" / "samename"
    b = tmp_path / "second" / "samename"
    a.parent.mkdir()
    b.parent.mkdir()
    _make_repo(a)
    _make_repo(b)

    runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(a), "-y"])
    result = runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(b), "-y"])
    assert result.exit_code == 1
    assert "worktree" in result.stderr.lower()


def test_add_with_explicit_worktree_name(projects, make_project, source_repo) -> None:
    make_project("foo")
    result = runner.invoke(
        app,
        [
            "code",
            "add",
            "--project",
            "foo",
            "--repo",
            str(source_repo),
            "--worktree",
            "code-custom",
            "-y",
        ],
    )
    assert result.exit_code == 0
    assert (projects / "foo" / "code-custom").is_dir()


def test_add_preserves_manifest_extensions(projects, make_project, source_repo) -> None:
    proj = make_project("foo")
    from keel.manifest import load_project_manifest, save_project_manifest

    m = load_project_manifest(proj / "project.toml")
    m.extensions = {"ai": {"enabled": False}}
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["code", "add", "--project", "foo", "--repo", str(source_repo)])
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(proj / "project.toml")
    assert m.extensions == {"ai": {"enabled": False}}
