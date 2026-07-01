"""`keel task rm <id>`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    confirm_destructive,
    edit_milestones,
    get_task,
    load_milestones_manifest,
    resolve_cli_scope,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("task.rm")
def cmd_rm(
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
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the confirm prompt."),
    force: bool = typer.Option(
        False, "--force", help="Remove even if other tasks depend on this one."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip task.rm.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a task. Refuses if other tasks depend on it (use --force to override)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-validate before write
    manifest = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    get_task(manifest, id, out=out)  # validate that task exists

    dependents = [t.id for t in manifest.tasks if id in t.depends_on]
    if dependents and not force:
        out.fail(
            f"cannot remove task '{id}'; depended on by: {', '.join(dependents)} "
            "(use --force to remove anyway)",
            code=ErrorCode.INVALID_STATE,
        )

    if dry_run:
        log = OpLog()
        log.modify_file(scope.milestones_manifest_path)
        out.info(log.format_summary())
        return

    confirm_destructive(f"Remove task {id}?", yes=yes)

    try:
        with hook_event(
            "task.rm",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                task_being_removed = get_task(manifest, id, out=out)
                old_milestone_id = task_being_removed.milestone

                manifest.tasks = [t for t in manifest.tasks if t.id != id]

                # If the old milestone was the implicit default and now empty, drop it.
                if old_milestone_id == "default" and not any(
                    t.milestone == "default" for t in manifest.tasks
                ):
                    manifest.milestones = [ms for ms in manifest.milestones if ms.id != "default"]
    except HookAborted as e:
        out.fail(
            f"task.rm aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result({"removed": id}, human_text=f"Task removed: {id}")
