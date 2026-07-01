"""`keel milestone done <id>`."""

from __future__ import annotations

import typer

from keel import workspace
from keel.api import (
    ErrorCode,
    OpLog,
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
def cmd_done(
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
    force: bool = typer.Option(False, "--force", help="Skip sub-milestone completion check."),
    no_push: bool = typer.Option(
        False,
        "--no-push",
        help="Skip pushing to the configured ticketing provider for this invocation.",
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip milestone.status.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Mark a milestone as done (active -> done)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-validate before write
    manifest = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    milestone = get_milestone(manifest, id, out=out)

    if milestone.status == "done":
        out.result(milestone.model_dump(), human_text=f"Milestone {id} is already done.")
        return

    if milestone.status != "active":
        out.fail(
            f"cannot mark milestone done from status '{milestone.status}' (must be 'active')",
            code=ErrorCode.INVALID_STATE,
        )

    if not force:
        # Check own tasks are all terminal (done or cancelled).
        incomplete_tasks = [
            f"{t.id} (status: {t.status})"
            for t in manifest.tasks
            if t.milestone == milestone.id and t.status not in ("done", "cancelled")
        ]
        if incomplete_tasks:
            out.fail(
                "cannot mark milestone done; tasks not complete: "
                + ", ".join(incomplete_tasks)
                + " (use --force to override)",
                code=ErrorCode.INVALID_STATE,
            )

        # Check sub-milestones in deliverables (only from project scope).
        if scope.deliverable is None:
            project_scope = workspace.Scope(project=scope.project)
            deliv_dir = project_scope.unit_dir / "deliverables"
            unfinished: list[str] = []
            if deliv_dir.is_dir():
                for child in sorted(deliv_dir.iterdir()):
                    if not child.is_dir():
                        continue
                    sub_scope = workspace.Scope(project=scope.project, deliverable=child.name)
                    sub_manifest = load_milestones_manifest(sub_scope.milestones_manifest_path)
                    for sub in sub_manifest.milestones:
                        if sub.parent == milestone.id and sub.status not in (
                            "done",
                            "cancelled",
                        ):
                            unfinished.append(f"{child.name}/{sub.id} (status: {sub.status})")
            if unfinished:
                out.fail(
                    "cannot mark milestone done; sub-milestones not complete: "
                    + ", ".join(unfinished)
                    + " (use --force to override)",
                    code=ErrorCode.INVALID_STATE,
                )

    if dry_run:
        log = OpLog()
        log.modify_file(scope.milestones_manifest_path)
        out.info(log.format_summary())
        return

    try:
        with hook_event(
            "milestone.status",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "from": milestone.status, "to": "done", "command": "done", "forced": force},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                milestone = get_milestone(manifest, id, out=out)
                milestone.status = "done"
    except HookAborted as e:
        out.fail(
            f"milestone.status aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None and provider.name in milestone.tickets:
        tid = milestone.tickets[provider.name]
        safe_push(out, "transition", lambda: provider.transition(tid, "done"))

    out.result(milestone.model_dump(), human_text=f"Milestone done: {id}")
