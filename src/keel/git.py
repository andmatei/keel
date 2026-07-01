"""Thin wrapper around git CLI for the operations the workspace needs.

Uses subprocess directly rather than a library — no extra dep, the surface
we use is small.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args[1:])} failed: {r.stderr.strip()}")
    return r.stdout


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    except GitError:
        return False
    return True


def default_branch(repo: Path) -> str:
    """Symbolic ref of origin/HEAD, fallback to current branch."""
    try:
        out = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo).strip()
        return out.removeprefix("refs/remotes/origin/")
    except GitError:
        out = _run(["git", "branch", "--show-current"], cwd=repo).strip()
        return out or "main"


def create_worktree(repo: Path, dest: Path, *, branch: str, base: str | None = None) -> None:
    if dest.exists():
        raise GitError(f"destination already exists: {dest}")
    base = base or default_branch(repo)
    _run(
        ["git", "-C", str(repo), "worktree", "add", str(dest), "-b", branch, base],
    )


def remove_worktree(dest: Path, *, force: bool = False) -> None:
    """Remove a git worktree at `dest`. If `force=True`, allow even if dirty."""
    args = ["git", "-C", str(dest), "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(dest))
    _run(args)


def is_worktree_dirty(worktree: Path) -> bool:
    out = _run(["git", "-C", str(worktree), "status", "--porcelain"])
    return bool(out.strip())


def git_user_slug(repo: Path) -> str:
    """Return git user.name lowercased and stripped of spaces/non-alphanumerics."""
    name = _run(["git", "-C", str(repo), "config", "user.name"]).strip()
    return "".join(ch for ch in name.lower() if ch.isalnum())


def current_branch(worktree: Path) -> str:
    return _run(["git", "-C", str(worktree), "branch", "--show-current"]).strip()


def rename_branch(repo: Path, *, old: str, new: str) -> None:
    _run(["git", "-C", str(repo), "branch", "-m", old, new])


def move_worktree(old_dest: Path, new_dest: Path) -> None:
    _run(["git", "-C", str(old_dest), "worktree", "move", str(old_dest), str(new_dest)])
