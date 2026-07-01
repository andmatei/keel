"""`keel task worktree <id>` — create a per-task git worktree at the task's branch.

Semantics: *ensure exists*. If the worktree already exists at the expected path
and is a valid git directory checked out on the right branch, the command prints
a confirmation and exits 0 (idempotent). If the path exists but is *not* a git
directory (stale dir), the command fails with a clear error rather than silently
overwriting. If it is a git directory but on the wrong branch, the command fails
with a clear error.
"""

from __future__ import annotations

from pathlib import Path

import typer

from keel import git
from keel.api import (
    ErrorCode,
    MissingDepBranch,
    Output,
    ProjectManifest,
    get_task,
    load_milestones_manifest,
    load_project_manifest,
    resolve_base,
    resolve_cli_scope,
)


def cmd_worktree(
    ctx: typer.Context,
    id: str = typer.Argument(...),
    deliverable: str | None = typer.Option(
        None,
        "-D",
        "--deliverable",
        help="Scope: a deliverable instead of the project. Auto-detected from CWD.",
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project name. Auto-detected from CWD if omitted.",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        "-r",
        help="Worktree-dir name (from project manifest's [[repos]]). Required when project has multiple repos.",
    ),
    base: str | None = typer.Option(
        None,
        "--base",
        help="Git ref to branch from. Overrides the depends_on heuristic.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Ensure a git worktree exists for a task at its recorded branch (idempotent)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    manifest = load_milestones_manifest(scope.milestones_manifest_path)

    task = get_task(manifest, id, out=out)

    if not task.branch:
        out.fail(
            f"task '{id}' has no branch recorded; run 'keel task start {id}' first",
            code=ErrorCode.INVALID_STATE,
        )

    # Locate the project (or deliverable) manifest to get repos.
    # Note: deliverables now also use ProjectManifest per the redesign.
    proj_m: ProjectManifest = load_project_manifest(scope.manifest_path)
    repos = proj_m.repos

    if not repos:
        out.fail(
            "no [[repos]] declared in the manifest; run 'keel code add' first",
            code=ErrorCode.NOT_FOUND,
        )

    if repo is not None:
        target = next((r for r in repos if r.worktree == repo), None)
        if target is None:
            out.fail(
                f"no repo with worktree dir '{repo}' found in manifest",
                code=ErrorCode.NOT_FOUND,
            )
    elif len(repos) > 1:
        names = ", ".join(r.worktree for r in repos)
        out.fail(
            f"project has multiple repos ({names}); use --repo NAME to choose one",
            code=ErrorCode.CONFLICTING_FLAGS,
            exit_code=2,
        )
    else:
        target = repos[0]

    # Compute destination path: <unit>/<worktree-dir>-<task-id>/
    unit_dir = scope.unit_dir
    dest = unit_dir / f"{target.worktree}-{task.id}"

    # Idempotency: check if the worktree already exists.
    if dest.exists():
        if git.is_git_repo(dest):
            actual_branch = git.current_branch(dest)
            if actual_branch == task.branch:
                # Already a valid git worktree on the right branch — nothing to do.
                out.result(
                    {"task": id, "branch": task.branch, "worktree": str(dest), "created": False},
                    human_text=f"Worktree already exists at {dest} (branch {task.branch})",
                )
                return
            else:
                out.fail(
                    f"worktree exists at {dest} but is on branch '{actual_branch}', expected '{task.branch}'",
                    code=ErrorCode.GIT_FAILED,
                )
        else:
            # Stale directory — not a git repo.
            out.fail(
                f"destination already exists but is not a git worktree: {dest}",
                code=ErrorCode.GIT_FAILED,
            )

    # Resolve base branch using the same heuristic as `task start`.
    try:
        branch_base = resolve_base(
            scope.milestones_manifest_path,
            task.depends_on,
            base,
        )
    except MissingDepBranch as exc:
        if exc.reason == "not found":
            out.fail(
                f"task '{exc.dep_id}' not found in manifest",
                code=ErrorCode.NOT_FOUND,
            )
        else:
            out.fail(
                f"task '{exc.dep_id}' has no branch; start that task first",
                code=ErrorCode.INVALID_STATE,
            )

    repo_path = Path(target.remote)
    try:
        git.create_worktree(repo_path, dest, branch=task.branch, base=branch_base)
    except git.GitError as err:
        out.fail(f"worktree creation failed: {err}", code=ErrorCode.GIT_FAILED)

    out.result(
        {"task": id, "branch": task.branch, "worktree": str(dest), "created": True},
        human_text=f"Worktree created at {dest} (branch {task.branch})",
    )
