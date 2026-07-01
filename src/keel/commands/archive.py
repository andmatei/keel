"""`keel archive`."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import typer

from keel import git_ops, workspace
from keel.api import ErrorCode, OpLog, Output, confirm_destructive
from keel.hooks import HookAborted, hook_event, hookable


@hookable("project.archive")
def cmd_archive(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None, help="Project name. Auto-detected from CWD if omitted."
    ),
    force: bool = typer.Option(False, "--force", help="Allow archive even if worktrees are dirty."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt."),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip project.archive.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Soft-delete a project: remove worktrees, move to ~/projects/.archive/."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(name, None, allow_deliverable=False, out=out)
    project = scope.project

    proj_dir = workspace.project_dir(project)
    today = date.today().isoformat()
    dest = workspace.projects_dir() / ".archive" / f"{project}-{today}"

    if dry_run:
        log = OpLog()
        log.modify_file(proj_dir, diff=f"move → {dest}")
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Archive project {project}? Will move {proj_dir} → {dest} (worktrees removed first).",
        yes=yes,
    )

    # Collect all git worktree directories under the project (manifest-declared + on-disk scan)
    def _collect_worktrees(root: Path) -> list[Path]:
        """Return all linked-worktree directories directly under `root`."""
        found = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            # A linked worktree has a `.git` file (not a directory)
            git_marker = child / ".git"
            if git_marker.is_file():
                found.append(child)
        return found

    removed_worktrees: int = 0

    # Fire pre-archive, do the work, fire post-archive.
    try:
        with hook_event(
            "project.archive",
            project=project,
            deliverable=None,
            payload={},
            positional_args=(project,),
            out=out,
            no_verify=no_verify,
        ) as ev:
            # Remove worktrees under the project root
            for wt in _collect_worktrees(proj_dir):
                try:
                    git_ops.remove_worktree(wt, force=force)
                    removed_worktrees += 1
                except git_ops.GitError as e:
                    out.fail(
                        f"can't remove worktree {wt}: {e} (use --force)", code=ErrorCode.GIT_FAILED
                    )

            # Also handle deliverable worktrees
            deliv_dir = proj_dir / "deliverables"
            if deliv_dir.is_dir():
                for d in sorted(deliv_dir.iterdir()):
                    if not d.is_dir():
                        continue
                    for wt in _collect_worktrees(d):
                        try:
                            git_ops.remove_worktree(wt, force=force)
                            removed_worktrees += 1
                        except git_ops.GitError as e:
                            out.fail(
                                f"can't remove worktree {wt}: {e} (use --force)",
                                code=ErrorCode.GIT_FAILED,
                            )

            # Move the project tree
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(proj_dir), str(dest))
            (dest / ".archived").write_text(f"archived: {today}\nfrom: {proj_dir}\n")

            ev.add_post_payload(
                {"archived_path": str(dest), "removed_worktrees": removed_worktrees}
            )
    except HookAborted as e:
        out.fail(
            f"project.archive aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"archived_to": str(dest), "removed_worktrees": removed_worktrees},
        human_text=f"Archived {project} to {dest}.",
    )
