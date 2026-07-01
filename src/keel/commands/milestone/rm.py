"""`keel milestone rm <id>`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Milestone,
    OpLog,
    Output,
    confirm_destructive,
    edit_milestones,
    get_milestone,
    load_milestones_manifest,
    resolve_cli_scope,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("milestone.rm")
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
        False,
        "--force",
        help="Remove even if not in cancelled state and even if tasks reference it.",
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip milestone.rm.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a milestone. Only allowed when status is 'cancelled' (or with --force)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-validate before write: load and validate conditions
    manifest = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    milestone = get_milestone(manifest, id, out=out)

    if milestone.status != "cancelled" and not force:
        out.fail(
            f"cannot remove milestone in status '{milestone.status}' "
            f"(only 'cancelled' allowed; use --force to override)",
            code=ErrorCode.INVALID_STATE,
        )

    referencing = [t.id for t in manifest.tasks if t.milestone == id]
    if referencing and not force:
        out.fail(
            f"cannot remove milestone '{id}'; tasks reference it: {', '.join(referencing)} "
            "(use --force to remove anyway)",
            code=ErrorCode.INVALID_STATE,
        )

    if dry_run:
        log = OpLog()
        log.modify_file(scope.milestones_manifest_path)
        out.info(log.format_summary())
        return

    confirm_destructive(f"Remove milestone {id}?", yes=yes)

    try:
        with (
            hook_event(
                "milestone.rm",
                project=scope.project,
                deliverable=scope.deliverable,
                payload={"id": id},
                positional_args=(id,),
                out=out,
                no_verify=no_verify,
            ),
            edit_milestones(scope) as manifest,
        ):
            if force and referencing:
                if id == "default":
                    manifest.tasks = [t for t in manifest.tasks if t.milestone != id]
                else:
                    if not any(m.id == "default" for m in manifest.milestones):
                        manifest.milestones.append(Milestone(id="default", title="Tasks"))
                    for task in manifest.tasks:
                        if task.milestone == id:
                            task.milestone = "default"
            manifest.milestones = [m for m in manifest.milestones if m.id != id]
    except HookAborted as e:
        out.fail(
            f"milestone.rm aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result({"removed": id}, human_text=f"Milestone removed: {id}")
