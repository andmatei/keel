"""`keel milestone cancel <id>`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Output,
    confirm_destructive,
    edit_milestones,
    get_milestone,
    load_milestones_manifest,
    resolve_cli_scope,
    safe_push,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("milestone.status")
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
        False, "--force", help="Allow cancelling a milestone that is already done."
    ),
    no_push: bool = typer.Option(
        False, "--no-push", help="Skip pushing to the configured ticketing provider."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip milestone.status.pre hooks."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip the confirm prompt."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Cancel a milestone (planned/active -> cancelled)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-validate before entering the write context manager.
    pre = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    milestone_pre = get_milestone(pre, id, out=out)
    if milestone_pre.status == "cancelled":
        out.result(milestone_pre.model_dump(), human_text=f"Milestone {id} is already cancelled.")
        return
    if milestone_pre.status == "done" and not force:
        out.fail(
            f"milestone {id} is already done (use --force to cancel a done milestone)",
            code=ErrorCode.INVALID_STATE,
        )

    confirm_destructive(f"Cancel milestone {id} (currently {milestone_pre.status})?", yes=yes)

    try:
        with hook_event(
            "milestone.status",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "from": milestone_pre.status, "to": "cancelled", "command": "cancel", "forced": force},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                milestone = get_milestone(manifest, id, out=out)
                milestone.status = "cancelled"
    except HookAborted as e:
        out.fail(
            f"milestone.status aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None and provider.name in milestone.tickets:
        tid = milestone.tickets[provider.name]
        safe_push(out, "transition", lambda: provider.transition(tid, "cancelled"))

    out.result(milestone.model_dump(), human_text=f"Milestone cancelled: {id}")
