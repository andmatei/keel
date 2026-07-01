"""Tests for auto-worktree creation on `keel task start` and idempotent `keel task worktree`.

Covers:
- `task start` auto-creates branch + worktree when a repo is configured
- `--no-worktree` flag skips git operations but still records branch + marks active
- No-repo case: emits a warning but still marks task active
- Stacked base branch: base comes from last dependency's branch
- `--base <ref>` overrides the depends_on heuristic
- Error: dependency has no branch recorded
- Error: multiple repos, no --repo given
- `task worktree` is idempotent: re-running when worktree already exists is a no-op
- `task worktree` fails clearly on stale (non-git) directory
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from keel.app import app
from keel.manifest import load_milestones_manifest

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _seed(proj: Path, monkeypatch) -> None:
    """Create milestone m1 + task t1 under proj and set CWD."""
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "First"])


def _add_source_repo(proj: Path, source_repo: Path) -> None:
    """Register source_repo in the project manifest via `code add`."""
    runner.invoke(app, ["code", "add", "--repo", str(source_repo)])


def _make_second_repo(tmp_path: Path) -> Path:
    """Create a minimal second git repo."""
    repo = tmp_path / "src2"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True, capture_output=True)
    (repo / "README").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


# ---------------------------------------------------------------------------
# `task start` auto-worktree creation
# ---------------------------------------------------------------------------


def test_start_auto_creates_worktree(projects, make_project, source_repo, monkeypatch) -> None:
    """When a repo is configured, `task start` creates the worktree automatically."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    result = runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # milestones.toml reflects active status + branch
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"
    assert m.tasks[0].branch == "feat/t1"

    # worktree directory was created
    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 1, f"expected one worktree dir, got: {candidates}"
    assert (candidates[0] / "README").is_file()


def test_start_auto_worktree_uses_default_branch_as_base(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """When task has no depends_on, worktree is branched from the repo default branch."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    result = runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"], catch_exceptions=False)
    assert result.exit_code == 0

    # The worktree was checked out from the default branch (main).
    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 1
    wt = candidates[0]
    # Verify branch name in worktree
    branch_out = subprocess.run(
        ["git", "branch", "--show-current"], cwd=wt, capture_output=True, text=True
    )
    assert branch_out.stdout.strip() == "feat/t1"


# ---------------------------------------------------------------------------
# `--no-worktree` flag
# ---------------------------------------------------------------------------


def test_start_no_worktree_skips_git(projects, make_project, source_repo, monkeypatch) -> None:
    """`--no-worktree` marks the task active but does not create a git worktree."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    result = runner.invoke(
        app, ["task", "start", "t1", "--branch", "feat/t1", "--no-worktree"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output

    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"
    assert m.tasks[0].branch == "feat/t1"

    # No worktree directory was created
    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 0


# ---------------------------------------------------------------------------
# No-repo case: warn but still mark active
# ---------------------------------------------------------------------------


def test_start_no_repo_warns_and_still_activates(projects, make_project, monkeypatch) -> None:
    """When no [[repos]] are declared, task is still marked active with a warning (not an error)."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    # Intentionally do NOT add a repo

    result = runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # Warning message mentions repos / worktree
    output = result.output + (result.stderr or "")
    assert "repos" in output.lower() or "worktree" in output.lower()

    # Task is still active
    m = load_milestones_manifest(proj / "milestones.toml")
    assert m.tasks[0].status == "active"
    assert m.tasks[0].branch is not None


# ---------------------------------------------------------------------------
# Stacked branches: base from depends_on
# ---------------------------------------------------------------------------


def test_start_uses_last_dependency_branch_as_base(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """When task has depends_on, the base branch for the worktree is the last dep's branch."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_source_repo(proj, source_repo)

    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "Base task"])
    runner.invoke(app, ["task", "add", "t2", "--milestone", "m1", "--title", "Stacked", "--depends-on", "t1"])

    # Start t1 first (records branch feat/t1 and creates worktree)
    r1 = runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"], catch_exceptions=False)
    assert r1.exit_code == 0, r1.output

    # Make an extra commit on feat/t1 so it diverges from main — otherwise both
    # branches point to the same commit and the branching-point assertion is vacuous.
    wt1_candidates = list(proj.glob("code-*-t1*"))
    assert len(wt1_candidates) == 1
    wt1 = wt1_candidates[0]
    (wt1 / "new_file.txt").write_text("change")
    subprocess.run(["git", "add", "."], cwd=wt1, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "extra commit"], cwd=wt1, check=True, capture_output=True)

    # Start t2: should use feat/t1 as base
    r2 = runner.invoke(app, ["task", "start", "t2", "--branch", "feat/t2"], catch_exceptions=False)
    assert r2.exit_code == 0, r2.output

    # t2 worktree exists
    candidates = list(proj.glob("code-*-t2*"))
    assert len(candidates) == 1
    wt2 = candidates[0]

    # The current branch in t2's worktree is feat/t2
    branch_out = subprocess.run(
        ["git", "branch", "--show-current"], cwd=wt2, capture_output=True, text=True
    )
    assert branch_out.stdout.strip() == "feat/t2"

    # Verify that feat/t2 was branched off feat/t1 (same commit hash as tip of feat/t1).
    # Because feat/t1 now has an extra commit that main doesn't, this assertion is
    # non-trivial: it would fail if t2 were branched off main instead of feat/t1.
    t1_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wt1, capture_output=True, text=True
    ).stdout.strip()
    t2_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wt2, capture_output=True, text=True
    ).stdout.strip()
    assert t1_head == t2_head, "t2 should have been branched from t1's tip"


def test_start_dependency_no_branch_fails(projects, make_project, source_repo, monkeypatch) -> None:
    """If a dependency task has no branch (was never started), start fails before touching git."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_source_repo(proj, source_repo)

    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "Base"])
    runner.invoke(app, ["task", "add", "t2", "--milestone", "m1", "--title", "Stacked", "--depends-on", "t1"])
    # t1 is NOT started — it has no branch

    result = runner.invoke(app, ["task", "start", "t2", "--branch", "feat/t2"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "t1" in combined
    assert "branch" in combined.lower() or "start" in combined.lower()


# ---------------------------------------------------------------------------
# `--base <ref>` explicit override
# ---------------------------------------------------------------------------


def test_start_explicit_base_overrides_depends_on(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """--base overrides the depends_on heuristic for base branch."""
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_source_repo(proj, source_repo)

    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "Base"])
    runner.invoke(app, ["task", "add", "t2", "--milestone", "m1", "--title", "Stacked", "--depends-on", "t1"])

    # Start t1 first (records branch feat/t1 and creates worktree).
    runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"], catch_exceptions=False)

    # Capture main's HEAD *before* making an extra commit on feat/t1.
    # This is the commit t2 should land on when --base main is passed.
    wt1_candidates = list(proj.glob("code-*-t1*"))
    assert len(wt1_candidates) == 1
    wt1 = wt1_candidates[0]
    main_tip_before_extra = subprocess.run(
        ["git", "rev-parse", "main"], cwd=wt1, capture_output=True, text=True
    ).stdout.strip()

    # Make an extra commit on feat/t1 so it diverges from main — this ensures
    # the explicit-base assertion is non-trivial (t2 must NOT include this commit).
    (wt1 / "new_file.txt").write_text("change")
    subprocess.run(["git", "add", "."], cwd=wt1, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "extra commit"], cwd=wt1, check=True, capture_output=True)

    # Start t2 with explicit --base pointing to 'main' instead of 'feat/t1'.
    result = runner.invoke(
        app, ["task", "start", "t2", "--branch", "feat/t2", "--base", "main"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output

    # t2's worktree should be branched from main (not from the advanced feat/t1 tip).
    candidates = list(proj.glob("code-*-t2*"))
    assert len(candidates) == 1
    wt2 = candidates[0]
    t2_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wt2, capture_output=True, text=True
    ).stdout.strip()

    # feat/t2 must start at main's tip (before the extra t1 commit), not at feat/t1's tip.
    assert t2_head == main_tip_before_extra, (
        f"feat/t2 should have been branched from main ({main_tip_before_extra}), "
        f"got {t2_head}"
    )

    # Sanity-check: feat/t1's tip is ahead of main, so if t2 had been branched
    # from feat/t1 the assertion above would have failed.
    t1_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wt1, capture_output=True, text=True
    ).stdout.strip()
    assert t1_head != main_tip_before_extra, "feat/t1 tip should differ from main after extra commit"


# ---------------------------------------------------------------------------
# Multiple repos: `--repo` is required
# ---------------------------------------------------------------------------


def test_start_multi_repo_requires_explicit_repo(
    projects, make_project, source_repo, monkeypatch, tmp_path
) -> None:
    """With multiple repos and no --repo, start fails with a clear error."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)

    second_repo = _make_second_repo(tmp_path)
    _add_source_repo(proj, source_repo)
    runner.invoke(app, ["code", "add", "--repo", str(second_repo)])

    result = runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"])
    assert result.exit_code != 0
    combined = result.output + (result.stderr or "")
    assert "repo" in combined.lower() or "--repo" in combined


def test_start_multi_repo_with_explicit_repo_succeeds(
    projects, make_project, source_repo, monkeypatch, tmp_path
) -> None:
    """With multiple repos, passing --repo picks the right one."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)

    second_repo = _make_second_repo(tmp_path)
    _add_source_repo(proj, source_repo)
    runner.invoke(app, ["code", "add", "--repo", str(second_repo)])

    # The worktree name for source_repo is "code-{repo.name}" = "code-_source_repo"
    primary_wt_name = f"code-{source_repo.name}"

    result = runner.invoke(
        app,
        ["task", "start", "t1", "--branch", "feat/t1", "--repo", primary_wt_name],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    # worktree exists under the primary repo's worktree dir
    candidates = list(proj.glob(f"{primary_wt_name}-t1*"))
    assert len(candidates) == 1


# ---------------------------------------------------------------------------
# `task worktree` idempotency
# ---------------------------------------------------------------------------


def test_task_worktree_idempotent(projects, make_project, source_repo, monkeypatch) -> None:
    """`task worktree` is a no-op if the worktree already exists at the expected branch."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    # Create via task start
    runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1"], catch_exceptions=False)

    # Re-run worktree — should succeed without error
    result = runner.invoke(app, ["task", "worktree", "t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # Still only one worktree dir
    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 1


def test_task_worktree_idempotent_after_explicit_worktree_call(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """`task worktree` called twice does not duplicate or error."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1", "--no-worktree"])

    # First explicit worktree call creates it
    r1 = runner.invoke(app, ["task", "worktree", "t1"], catch_exceptions=False)
    assert r1.exit_code == 0

    # Second explicit worktree call is idempotent
    r2 = runner.invoke(app, ["task", "worktree", "t1"], catch_exceptions=False)
    assert r2.exit_code == 0

    candidates = list(proj.glob("code-*-t1*"))
    assert len(candidates) == 1


def test_task_worktree_stale_dir_fails_clearly(
    projects, make_project, source_repo, monkeypatch
) -> None:
    """`task worktree` fails with a clear error if dest exists but is not a git worktree."""
    proj = make_project("foo")
    _seed(proj, monkeypatch)
    _add_source_repo(proj, source_repo)

    runner.invoke(app, ["task", "start", "t1", "--branch", "feat/t1", "--no-worktree"])

    # Manually place a non-git directory at the expected dest.
    # `code add` names the worktree "code-{repo_basename}" — for the `source_repo` fixture
    # the repo basename is "_source_repo", so the worktree dir is "code-_source_repo".
    # The task worktree dest is then "<worktree>-<task_id>", i.e. "code-_source_repo-t1".
    dest = proj / f"code-{source_repo.name}-t1"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("stale")

    result = runner.invoke(app, ["task", "worktree", "t1"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr or "")
    assert "exist" in combined.lower() or "stale" in combined.lower() or "git" in combined.lower()
