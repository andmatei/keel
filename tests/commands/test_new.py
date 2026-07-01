"""Tests for `keel new`."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_project_manifest

runner = CliRunner()


def test_new_creates_unit_layout(projects) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "A test project", "--no-worktree", "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, (result.stdout, result.stderr)
    proj = projects / "foo"
    assert (proj / "scope.md").is_file()
    assert (proj / "design.md").is_file()
    assert (proj / "README.md").is_file()
    assert (proj / "project.toml").is_file()
    assert (proj / "decisions").is_dir()
    assert (proj / ".keel" / "phase").read_text().splitlines()[0] == "scoping"


def test_new_writes_valid_manifest(projects) -> None:
    runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.name == "foo"
    assert m.project.description == "test"
    assert m.repos == []


def test_new_fails_if_project_exists(projects) -> None:
    runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
    result = runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
    assert result.exit_code == 1
    assert "already exists" in result.stderr


def test_new_fails_without_description_non_tty(projects) -> None:
    """When stdin is not a tty, missing --description exits with code 2."""
    result = runner.invoke(app, ["new", "foo", "--no-worktree", "-y"], input="")
    assert result.exit_code == 2


def test_new_json_output(projects) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "t", "--no-worktree", "-y", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["path"].endswith("/foo")
    assert payload["worktrees"] == []
    # JSON mode suppresses info logs:
    assert "Created project" not in result.stderr


def test_new_with_one_repo_creates_worktree(projects, source_repo) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "t", "-r", str(source_repo), "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert (projects / "foo" / "code").is_dir()
    assert (projects / "foo" / "code" / "README").is_file()


def test_new_with_one_repo_writes_repo_to_manifest(projects, source_repo) -> None:
    runner.invoke(app, ["new", "foo", "-d", "t", "-r", str(source_repo), "-y"])
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert len(m.repos) == 1
    assert m.repos[0].worktree == "code"


def test_new_with_invalid_repo_exits_1(projects, tmp_path) -> None:
    not_a_repo = tmp_path / "nope"
    not_a_repo.mkdir()
    result = runner.invoke(app, ["new", "foo", "-d", "t", "-r", str(not_a_repo), "-y"])
    assert result.exit_code == 1
    assert "not a git repo" in result.stderr.lower()


def test_new_with_two_repos_creates_named_worktrees(projects, tmp_path) -> None:
    import subprocess

    repos = []
    for name in ("alpha", "beta"):
        r = tmp_path / f"src_{name}"
        r.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=r, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=r, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=r, check=True)
        (r / "README").write_text(name)
        subprocess.run(["git", "add", "."], cwd=r, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=r, check=True, capture_output=True)
        repos.append(str(r))
    result = runner.invoke(
        app,
        ["new", "multi", "-d", "two repos", "-r", repos[0], "-r", repos[1], "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert (projects / "multi" / "code-src_alpha").is_dir()
    assert (projects / "multi" / "code-src_beta").is_dir()
    m = load_project_manifest(projects / "multi" / "project.toml")
    assert len(m.repos) == 2
    worktrees = {r.worktree for r in m.repos}
    assert worktrees == {"code-src_alpha", "code-src_beta"}


def test_new_dry_run_writes_nothing(projects, source_repo) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "t", "-r", str(source_repo), "--dry-run", "-y"],
    )
    assert result.exit_code == 0
    assert not (projects / "foo").exists()


def test_new_dry_run_lists_planned_ops(projects, source_repo) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "t", "-r", str(source_repo), "--dry-run", "-y"],
    )
    assert "[dry-run]" in result.stderr
    assert "project.toml" in result.stderr
    assert "scope.md" in result.stderr
    assert "design.md" in result.stderr
    assert "README.md" in result.stderr
    assert "lifecycle.lock.toml" in result.stderr
    assert "git worktree" in result.stderr.lower()


def test_new_does_not_print_duplicate_messages(projects) -> None:
    """The 'Created project: ...' (stderr) was redundant with 'Project created: ...' (stdout); only one survives."""
    result = runner.invoke(app, ["new", "foo", "-d", "t", "--no-worktree", "-y"])
    # The success line is on stdout; stderr should NOT also have a near-identical 'Created project:' line.
    assert "Created project:" not in result.stderr
    # The result line itself remains:
    assert result.stdout  # non-empty


def test_new_records_lifecycle_in_manifest(projects, monkeypatch) -> None:
    """`keel new <name> --lifecycle <id>` writes the field to project.toml."""
    monkeypatch.chdir(projects)
    runner.invoke(
        app, ["new", "alpha", "-d", "test", "--no-worktree", "-y", "--lifecycle", "default"]
    )
    m = load_project_manifest(projects / "alpha" / "project.toml")
    assert m.project.lifecycle == "default"


def test_new_default_lifecycle_when_omitted(projects, monkeypatch) -> None:
    """When --lifecycle is omitted, the manifest gets 'default'."""
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "test", "--no-worktree", "-y"])
    m = load_project_manifest(projects / "alpha" / "project.toml")
    assert m.project.lifecycle == "default"


def test_new_unknown_lifecycle_fails(projects, monkeypatch) -> None:
    """`--lifecycle ghost` exits non-zero with a clear error."""
    monkeypatch.chdir(projects)
    result = runner.invoke(
        app, ["new", "alpha", "-d", "test", "--no-worktree", "-y", "--lifecycle", "ghost"]
    )
    assert result.exit_code != 0
    assert "ghost" in result.stderr.lower() or "lifecycle" in result.stderr.lower()


def test_new_uses_lifecycle_initial_phase(projects, make_project, monkeypatch) -> None:
    """The new project's phase file is set to the lifecycle's initial state."""
    # Create a custom lifecycle with a non-'scoping' initial state.
    lib = projects / ".keel" / "lifecycles"
    lib.mkdir(parents=True)
    (lib / "research.toml").write_text(
        """
name = "research"
initial = "proposing"
terminal = ["published"]
[states.proposing]
[states.published]
[transitions]
proposing = ["published"]
""".strip()
    )
    monkeypatch.chdir(projects)
    runner.invoke(
        app, ["new", "alpha", "-d", "test", "--no-worktree", "-y", "--lifecycle", "research"]
    )
    phase_text = (projects / "alpha" / ".keel" / "phase").read_text().strip()
    assert phase_text == "proposing"


def test_new_writes_project_toml_at_root(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    result = runner.invoke(app, ["new", "alpha", "-d", "test", "--no-worktree", "-y"])
    assert result.exit_code == 0
    assert (projects / "alpha" / "project.toml").is_file()
    assert not (projects / "alpha" / "design" / "project.toml").exists()


def test_new_writes_phase_under_keel(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "test", "--no-worktree", "-y"])
    assert (projects / "alpha" / ".keel" / "phase").read_text().strip() == "scoping"


def test_new_writes_lifecycle_lock(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "test", "--no-worktree", "-y"])
    lock = projects / "alpha" / ".keel" / "lifecycle.lock.toml"
    assert lock.is_file()
    text = lock.read_text()
    # Verbatim copy of the default lifecycle TOML.
    assert 'name = "default"' in text
    assert "[states.scoping]" in text


def test_new_writes_readme_with_links(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "Build a thing", "--no-worktree", "-y"])
    readme = (projects / "alpha" / "README.md").read_text()
    assert "alpha" in readme
    assert "Build a thing" in readme
    assert "[Scope](scope.md)" in readme
    assert "[Design](design.md)" in readme


def test_new_human_design_files_at_root(projects, monkeypatch) -> None:
    monkeypatch.chdir(projects)
    runner.invoke(app, ["new", "alpha", "-d", "test", "--no-worktree", "-y"])
    assert (projects / "alpha" / "scope.md").is_file()
    assert (projects / "alpha" / "design.md").is_file()
    assert (projects / "alpha" / "decisions").is_dir()
    # design/ subfolder MUST NOT be created in the new layout
    assert not (projects / "alpha" / "design").exists()


# ---------------------------------------------------------------------------
# Task 3.1: hook_event wiring (pre-new / post-new) + --no-verify
# ---------------------------------------------------------------------------


def test_new_fires_pre_and_post_subscribers(projects, monkeypatch) -> None:
    """Both pre-new and post-new fire around a successful keel new."""
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.builtin_listeners import register_builtin_listeners
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    register_builtin_listeners()
    try:
        fired: list[str] = []

        @subscribes_to("project.create.pre")
        def pre(event: HookEvent, *, out) -> None:
            fired.append(event.full_name)

        @subscribes_to("project.create.post")
        def post(event: HookEvent, *, out) -> None:
            fired.append(event.full_name)
            # Post payload contains 'path'
            assert "path" in event.payload

        runner = CliRunner()
        monkeypatch.chdir(projects)
        result = runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
        assert result.exit_code == 0
        assert fired == ["project.create.pre", "project.create.post"]
    finally:
        _clear_registry()
        register_builtin_listeners()


def test_new_pre_hook_can_block(projects, monkeypatch) -> None:
    """A pre-new subscriber raising HookAborted aborts the command."""
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookAborted, HookEvent, subscribes_to
    from keel.hooks.builtin_listeners import register_builtin_listeners
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    register_builtin_listeners()
    try:

        @subscribes_to("project.create.pre")
        def block(event: HookEvent, *, out) -> None:
            raise HookAborted("not allowed")

        runner = CliRunner()
        monkeypatch.chdir(projects)
        result = runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
        assert result.exit_code != 0
        assert "not allowed" in result.stderr
        # No project dir created
        assert not (projects / "foo").exists()
    finally:
        _clear_registry()
        register_builtin_listeners()


def test_new_no_verify_bypasses_pre_hook(projects, monkeypatch) -> None:
    """--no-verify skips pre-new subscribers."""
    from typer.testing import CliRunner

    from keel.app import app
    from keel.hooks import HookAborted, HookEvent, subscribes_to
    from keel.hooks.builtin_listeners import register_builtin_listeners
    from keel.hooks.registry import _clear_registry

    _clear_registry()
    register_builtin_listeners()
    try:

        @subscribes_to("project.create.pre")
        def block(event: HookEvent, *, out) -> None:
            raise HookAborted("not allowed")

        runner = CliRunner()
        monkeypatch.chdir(projects)
        result = runner.invoke(
            app, ["new", "foo", "-d", "test", "--no-worktree", "-y", "--no-verify"]
        )
        assert result.exit_code == 0
        assert (projects / "foo" / "project.toml").is_file()
    finally:
        _clear_registry()
        register_builtin_listeners()


def test_new_with_tags(projects) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "test", "--no-worktree", "-y", "--tag", "api", "--tag", "webhook"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert set(m.project.tags) == {"api", "webhook"}


def test_new_with_invalid_tag_fails(projects) -> None:
    result = runner.invoke(
        app,
        ["new", "foo", "-d", "test", "--no-worktree", "-y", "--tag", "bad tag!"],
    )
    assert result.exit_code != 0


def test_new_without_tags_has_empty_list(projects) -> None:
    runner.invoke(app, ["new", "foo", "-d", "test", "--no-worktree", "-y"])
    m = load_project_manifest(projects / "foo" / "project.toml")
    assert m.project.tags == []
