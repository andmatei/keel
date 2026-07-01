"""`keel rename` (project-level)."""

from __future__ import annotations

import shutil

import typer

from keel import git, workspace
from keel.api import (
    HINT_LIST_PROJECTS,
    ErrorCode,
    OpLog,
    Output,
    confirm_destructive,
    load_project_manifest,
    save_project_manifest,
    slugify,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("project.rename")
def cmd_rename(
    ctx: typer.Context,
    old: str = typer.Argument(..., help="Current project name."),
    new: str = typer.Argument(..., help="New project name (will be slugified)."),
    rename_branches: bool = typer.Option(
        True,
        "--rename-branches/--no-rename-branches",
        help="Rename worktree branches to use the new project's branch_prefix.",
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip project.rename.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Rename a project — directory, worktrees, branch prefixes, deliverable references."""
    out = Output.from_context(ctx, json_mode=json_mode)
    new_slug = slugify(new)
    if not new_slug:
        out.fail("invalid new project name", code=ErrorCode.INVALID_NAME, exit_code=2)

    if not workspace.project_exists(old):
        out.fail(f"project not found: {old}\n  {HINT_LIST_PROJECTS}", code=ErrorCode.NOT_FOUND)
    if workspace.project_exists(new_slug):
        out.fail(f"target project already exists: {new_slug}", code=ErrorCode.EXISTS)

    old_path = workspace.project_dir(old)
    new_path = workspace.project_dir(new_slug)
    old_scope = workspace.Scope(project=old, deliverable=None)
    new_scope = workspace.Scope(project=new_slug, deliverable=None)

    if dry_run:
        log = OpLog()
        log.modify_file(old_path, diff=f"rename → {new_path}")
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Rename project {old} → {new_slug}? Worktrees and branches will move.",
        yes=yes,
    )

    branch_renames: list[tuple[str, str]] = []

    try:
        with hook_event(
            "project.rename",
            project=new_slug,
            deliverable=None,
            payload={"old_name": old, "new_name": new_slug},
            positional_args=(old, new_slug),
            out=out,
            no_verify=no_verify,
        ) as ev:
            m = load_project_manifest(old_scope.manifest_path)

            new_path.mkdir(parents=True, exist_ok=True)

            new_repos = []
            for r in m.repos:
                old_wt = old_path / r.worktree
                new_wt = new_path / r.worktree
                if old_wt.is_dir():
                    git.move_worktree(old_wt, new_wt)
                    if rename_branches and r.branch_prefix and old in r.branch_prefix:
                        old_branch = git.current_branch(new_wt)
                        if old_branch and old_branch.startswith(r.branch_prefix):
                            new_branch_prefix = r.branch_prefix.replace(old, new_slug, 1)
                            new_branch = old_branch.replace(r.branch_prefix, new_branch_prefix, 1)
                            git.rename_branch(new_wt, old=old_branch, new=new_branch)
                            branch_renames.append((old_branch, new_branch))
                            r = r.model_copy(update={"branch_prefix": new_branch_prefix})
                new_repos.append(r)

            for child in list(old_path.iterdir()):
                if (new_path / child.name).exists():
                    continue
                shutil.move(str(child), str(new_path / child.name))

            if old_path.exists() and not any(old_path.iterdir()):
                old_path.rmdir()

            new_manifest = m.model_copy(
                update={
                    "project": m.project.model_copy(update={"name": new_slug}),
                    "repos": new_repos,
                }
            )
            save_project_manifest(new_scope.manifest_path, new_manifest)

            ev.add_post_payload({"branch_renames": branch_renames})
    except HookAborted as e:
        out.fail(
            f"project.rename aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"old": old, "new": new_slug, "branch_renames": branch_renames},
        human_text=f"Renamed {old} → {new_slug} (branches: {len(branch_renames)}).",
    )
