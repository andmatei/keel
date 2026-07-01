"""Tests for `keel task worktree`."""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


@pytest.fixture
def source_repo(tmp_path) -> Path:
    """A bare-minimum git repo with a single initial commit on main."""
    repo = tmp_path / "src"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True
    )
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_task_worktree_creates_branch_worktree(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """`task worktree t1` creates a git worktree at the task's branch."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Add the source repo to the project
    runner.invoke(app, ["code", "add", "--repo", str(source_repo)])
    # Add a milestone + task and start it (records a branch)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "x"])
    runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1", "--no-worktree"])

    result = runner.invoke(app, ["task", "worktree", "t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.stderr
    # The new worktree dir exists somewhere under the project unit
    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 1
    assert (candidates[0] / "README.md").is_file()


def test_task_worktree_unknown_id_fails(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    result = runner.invoke(app, ["task", "worktree", "nothing"])
    assert result.exit_code == 1


def test_task_worktree_no_branch_recorded_fails(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """If the task has no branch (never started), worktree fails clearly."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["code", "add", "--repo", str(source_repo)])
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "x"])
    # Don't start; branch is None
    result = runner.invoke(app, ["task", "worktree", "t1"])
    assert result.exit_code == 1
    assert "branch" in result.stderr.lower() or "not started" in result.stderr.lower()


def test_task_worktree_multi_repo_requires_explicit_repo(
    projects, make_project, source_repo, monkeypatch, tmp_path
) -> None:
    """When the project has multiple repos, --repo is required."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    # Add two source repos so the project has multiple [[repos]] entries.
    second_repo = tmp_path / "src2"
    second_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=second_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=second_repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=second_repo, check=True)
    (second_repo / "README").write_text("x")
    subprocess.run(["git", "add", "."], cwd=second_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=second_repo, check=True, capture_output=True
    )

    runner.invoke(app, ["code", "add", "--repo", str(source_repo)])
    runner.invoke(app, ["code", "add", "--repo", str(second_repo)])
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "x"])
    start = runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1", "--no-worktree"])
    assert start.exit_code == 0, start.stderr

    result = runner.invoke(app, ["task", "worktree", "t1"])
    assert result.exit_code == 2  # CONFLICTING_FLAGS exit code
    combined = result.stderr.lower() + result.stdout.lower()
    assert "multiple repos" in combined or "--repo" in combined
