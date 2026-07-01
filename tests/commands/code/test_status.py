# tests/commands/code/test_status.py
"""Tests for `keel code status`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_status_no_repos(projects, make_project) -> None:
    make_project("foo")
    result = runner.invoke(app, ["code", "status", "--project", "foo"])
    assert result.exit_code == 0


def test_status_repo_not_cloned(projects, make_project) -> None:
    """When local_hint points at a missing dir, status reports 'missing'."""
    from datetime import date

    from keel.manifest import (
        ProjectManifest,
        ProjectMeta,
        RepoSpec,
        save_project_manifest,
    )

    proj = make_project("foo")
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[
            RepoSpec(
                remote="git@e.com:o/r.git",
                local_hint=str(projects / "_missing"),
                worktree="code",
                branch_prefix="a/foo",
            )
        ],
    )
    save_project_manifest(proj / "project.toml", m)
    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["repos"][0]["cloned"] is False
    assert payload["repos"][0]["worktree_exists"] is False


def test_status_worktree_clean(projects, make_project, source_repo) -> None:
    """A live worktree on the right branch is reported as clean."""
    from datetime import date

    from keel import git
    from keel.manifest import (
        ProjectManifest,
        ProjectMeta,
        RepoSpec,
        save_project_manifest,
    )

    proj = make_project("foo")
    branch = "alice/foo-base"
    git.create_worktree(source_repo, proj / "code", branch=branch)

    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[
            RepoSpec(
                remote=str(source_repo),
                local_hint=str(source_repo),
                worktree="code",
                branch_prefix=branch,
            )
        ],
    )
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    repo = payload["repos"][0]
    assert repo["cloned"] is True
    assert repo["worktree_exists"] is True
    assert repo["dirty"] is False
    assert repo["branch"] == branch


def test_status_worktree_dirty(projects, make_project, source_repo) -> None:
    from datetime import date

    from keel import git
    from keel.manifest import (
        ProjectManifest,
        ProjectMeta,
        RepoSpec,
        save_project_manifest,
    )

    proj = make_project("foo")
    git.create_worktree(source_repo, proj / "code", branch="alice/foo-base")
    (proj / "code" / "dirty.txt").write_text("not committed")

    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        repos=[
            RepoSpec(
                remote=str(source_repo),
                local_hint=str(source_repo),
                worktree="code",
                branch_prefix="alice/foo-base",
            )
        ],
    )
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["code", "status", "--project", "foo", "--json"])
    payload = json.loads(result.stdout)
    assert payload["repos"][0]["dirty"] is True
