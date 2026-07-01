"""`keel code rm`."""

from __future__ import annotations

import typer

from keel import git, workspace
from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    confirm_destructive,
    edit_project_manifest,
    load_project_manifest,
)


def cmd_rm(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Remove from deliverable scope."
    ),
    repo: str = typer.Option(..., "--repo", "-r", help="Remote URL of the repo to remove."),
    force: bool = typer.Option(
        False, "--force", help="Allow removal even if the worktree has uncommitted changes."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a repo from the manifest and remove its worktree."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    manifest_path = scope.manifest_path
    m = load_project_manifest(manifest_path)

    target = next((r for r in m.repos if r.remote == repo), None)
    if target is None:
        out.fail(f"no repo with remote: {repo}", code=ErrorCode.NOT_FOUND)

    unit_dir = scope.unit_dir
    wt_path = unit_dir / target.worktree

    if dry_run:
        log = OpLog()
        log.modify_file(manifest_path, diff=f"- [[repos]] remote={repo}")
        if wt_path.is_dir():
            log.remove_worktree(wt_path)
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Remove repo {repo} and its worktree at {wt_path}?",
        yes=yes,
    )

    # Remove worktree first; if dirty and not --force, abort before manifest mutation
    if wt_path.is_dir():
        try:
            git.remove_worktree(wt_path, force=force)
        except git.GitError as e:
            out.fail(
                f"worktree removal failed (use --force if dirty): {e}", code=ErrorCode.GIT_FAILED
            )

    with edit_project_manifest(manifest_path) as manifest:
        manifest.repos = [r for r in manifest.repos if r.remote != repo]

    out.result(
        {
            "removed": target.worktree,
            "remote": repo,
            "worktree_path": str(wt_path),
        },
        human_text=f"Removed: {repo}",
    )
