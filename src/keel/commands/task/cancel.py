"""`keel task cancel <id>`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Output,
    confirm_destructive,
    edit_milestones,
    get_task,
    load_milestones_manifest,
    resolve_cli_scope,
    safe_push,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("task.status")
def cmd_cancel(
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
    force: bool = typer.Option(
        False, "--force", help="Allow cancelling a task that is already done."
    ),
    no_push: bool = typer.Option(
        False, "--no-push", help="Skip pushing to the configured ticketing provider."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip task.status.pre hooks."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the confirm prompt."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Cancel a task (planned/active -> cancelled)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-validate before entering the write context manager.
    pre = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    task_pre = get_task(pre, id, out=out)
    from_status = task_pre.status
    if task_pre.status == "cancelled":
        out.result(task_pre.model_dump(), human_text=f"Task {id} is already cancelled.")
        return
    if task_pre.status == "done" and not force:
        out.fail(
            f"task {id} is already done (use --force to cancel a done task)",
            code=ErrorCode.INVALID_STATE,
        )

    confirm_destructive(f"Cancel task {id} (currently {task_pre.status})?", yes=yes)

    try:
        with hook_event(
            "task.status",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "from": from_status, "to": "cancelled", "command": "cancel", "forced": force},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                task = get_task(manifest, id, out=out)
                task.status = "cancelled"
    except HookAborted as e:
        out.fail(
            f"task.status aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None and provider.name in task.tickets:
        tid = task.tickets[provider.name]
        safe_push(out, "transition", lambda: provider.transition(tid, "cancelled"))

    out.result(task.model_dump(), human_text=f"Task cancelled: {id}")
