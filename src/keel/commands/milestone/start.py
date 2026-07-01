"""`keel milestone start <id>`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Output,
    edit_milestones,
    get_milestone,
    load_milestones_manifest,
    resolve_cli_scope,
    safe_push,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("milestone.status")
def cmd_start(
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
    reopen: bool = typer.Option(
        False, "--reopen", help="Allow re-opening a milestone that's already done or cancelled."
    ),
    no_push: bool = typer.Option(
        False, "--no-push", help="Skip pushing to the configured ticketing provider."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip milestone.status.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Start work on a milestone (planned -> active)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-load to capture current status before mutation.
    pre = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    pre_ms = get_milestone(pre, id, out=out)
    from_status = pre_ms.status

    try:
        with hook_event(
            "milestone.status",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "from": from_status, "to": "active", "command": "start", "forced": reopen},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                milestone = get_milestone(manifest, id, out=out)

                allowed = milestone.status == "planned" or (
                    milestone.status in ("done", "cancelled") and reopen
                )
                if allowed:
                    milestone.status = "active"
                elif milestone.status in ("done", "cancelled"):
                    out.fail(
                        f"cannot start milestone in status '{milestone.status}' "
                        f"(use --reopen to re-open a done or cancelled milestone)",
                        code=ErrorCode.INVALID_STATE,
                    )
                else:
                    out.fail(
                        f"cannot start milestone in status '{milestone.status}'",
                        code=ErrorCode.INVALID_STATE,
                    )
    except HookAborted as e:
        out.fail(
            f"milestone.status aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None and provider.name in milestone.tickets:
        tid = milestone.tickets[provider.name]
        safe_push(out, "transition", lambda: provider.transition(tid, "active"))

    out.result(milestone.model_dump(), human_text=f"Milestone started: {id}")
