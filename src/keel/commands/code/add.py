"""`keel code add`."""

from __future__ import annotations

from pathlib import Path

import typer

from keel import git, workspace
from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    RepoSpec,
    edit_project_manifest,
    load_project_manifest,
)


def cmd_add(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Add the repo at deliverable scope."
    ),
    repo: str = typer.Option(..., "--repo", "-r", help="Source git repo path."),
    worktree: str | None = typer.Option(
        None,
        "--worktree",
        help="Override the worktree dir name (default: derived from repo basename).",
    ),
    branch_prefix: str | None = typer.Option(
        None, "--branch-prefix", help="Override the branch prefix."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip interactive prompts."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Add a source repo to the manifest and create its worktree."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    repo_path = Path(repo).expanduser().resolve()
    if not git.is_git_repo(repo_path):
        out.fail(f"not a git repo: {repo_path}", code=ErrorCode.NOT_A_REPO)

    # Decide worktree dir name — derived from repo basename, prefixed with "code-".
    # An explicit --worktree always wins.
    wt_name = worktree or f"code-{repo_path.name}"

    # Derive branch prefix if not supplied
    if branch_prefix is None:
        try:
            user_slug = git.git_user_slug(repo_path)
        except Exception:
            user_slug = "user"
        suffix = f"-{deliverable}" if deliverable else ""
        branch_prefix = f"{user_slug}/{project}{suffix}-{repo_path.name}"

    # Load manifest
    manifest_path = scope.manifest_path
    m = load_project_manifest(manifest_path)
    if m.project.shared_worktree:
        out.fail(
            "cannot add repo to a shared-worktree deliverable",
            code=ErrorCode.INVALID_STATE,
        )

    # Detect duplicates
    for existing in m.repos:
        if existing.remote == str(repo_path):
            out.fail(
                f"duplicate remote: {repo_path} already declared", code=ErrorCode.DUPLICATE_REMOTE
            )
        if existing.worktree == wt_name:
            out.fail(
                f"worktree name '{wt_name}' already in use. Pass --worktree NAME to disambiguate.",
                code=ErrorCode.DUPLICATE_WORKTREE,
            )

    new_spec = RepoSpec(
        remote=str(repo_path),
        local_hint=str(repo_path),
        worktree=wt_name,
        branch_prefix=branch_prefix,
    )

    unit_dir = scope.unit_dir

    if dry_run:
        log = OpLog()
        log.modify_file(manifest_path, diff=f"+ [[repos]] remote={repo_path} worktree={wt_name}")
        log.create_worktree(unit_dir / wt_name, source=repo_path, branch=branch_prefix)
        out.info(log.format_summary())
        return

    try:
        git.create_worktree(repo_path, unit_dir / wt_name, branch=branch_prefix)
    except git.GitError as e:
        out.fail(f"worktree creation failed: {e}", code=ErrorCode.GIT_FAILED)

    with edit_project_manifest(manifest_path) as manifest:
        manifest.repos.append(new_spec)

    out.result(
        {
            "remote": str(repo_path),
            "worktree": str(unit_dir / wt_name),
            "branch_prefix": branch_prefix,
        },
        human_text=f"Repo added: {repo_path}",
    )
