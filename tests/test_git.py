"""Tests for the git wrapper.

Uses real git repos in tmp_path — no mocks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from keel.git import (
    GitError,
    create_worktree,
    default_branch,
    git_user_slug,
    is_git_repo,
    is_worktree_dirty,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / "README").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=Test User", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_is_git_repo_true(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    assert is_git_repo(repo) is True


def test_is_git_repo_false(tmp_path) -> None:
    assert is_git_repo(tmp_path) is False


def test_default_branch_main(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    assert default_branch(repo) == "main"


def test_create_worktree_creates_branch_and_dir(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    create_worktree(repo, wt, branch="me/feat")
    assert wt.is_dir()
    assert (wt / "README").read_text() == "test\n"
    # Branch exists in the repo:
    out = subprocess.run(
        ["git", "branch", "--list", "me/feat"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "me/feat" in out


def test_create_worktree_fails_if_dest_exists(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    wt.mkdir()
    with pytest.raises(GitError):
        create_worktree(repo, wt, branch="me/feat")


def test_is_worktree_dirty_clean(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    create_worktree(repo, wt, branch="me/feat")
    assert is_worktree_dirty(wt) is False


def test_is_worktree_dirty_with_change(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    create_worktree(repo, wt, branch="me/feat")
    (wt / "new.txt").write_text("dirty")
    assert is_worktree_dirty(wt) is True


def test_git_user_slug(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Andrei Matei"], cwd=repo, check=True)
    assert git_user_slug(repo) == "andreimatei"


def test_create_then_remove_worktree(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    create_worktree(repo, wt, branch="me/feat")
    assert wt.is_dir()
    from keel.git import remove_worktree

    remove_worktree(wt)
    assert not wt.exists()


def test_remove_worktree_dirty_fails_without_force(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    wt = tmp_path / "wt"
    create_worktree(repo, wt, branch="me/feat")
    (wt / "dirty.txt").write_text("dirty")
    from keel.git import GitError, remove_worktree

    with pytest.raises(GitError):
        remove_worktree(wt)
    # With force=True, it should succeed
    remove_worktree(wt, force=True)
    assert not wt.exists()
