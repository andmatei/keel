"""`keel task add <id> --milestone <m-id> --title "..."`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    GraphError,
    Milestone,
    OpLog,
    Output,
    Task,
    edit_milestones,
    find_task,
    load_milestones_manifest,
    resolve_cli_scope,
    safe_push,
    validate_dag,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("task.create")
def cmd_add(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Task identifier (e.g., 't1', 'set-up')."),
    title: str = typer.Option(..., "--title", help="Human-readable task title."),
    milestone: str | None = typer.Option(
        None,
        "--milestone",
        "-m",
        help="Milestone id. If omitted, an implicit 'default' milestone is auto-created.",
    ),
    description: str | None = typer.Option(None, "--description", help="Optional description."),
    depends_on: str = typer.Option(
        "",
        "--depends-on",
        help="Comma-separated list of task ids this task depends on.",
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Scope: a deliverable."
    ),
    project: str | None = typer.Option(None, "--project", "-p", help="Project name."),
    no_push: bool = typer.Option(
        False,
        "--no-push",
        help="Skip pushing to the configured ticketing provider.",
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip task.create.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON to stdout."),
) -> None:
    """Add a new task under a milestone (auto-creates 'default' if omitted)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    target_milestone_id = milestone or "default"

    # Pre-load manifest to validate before write
    manifest = load_milestones_manifest(scope.milestones_manifest_path)

    # If --milestone was passed and it doesn't exist, fail (existing behavior).
    # If --milestone was omitted, the 'default' milestone is auto-created below.
    if milestone is not None and not any(m.id == milestone for m in manifest.milestones):
        out.fail(
            f"unknown milestone '{milestone}' (use 'keel milestone list' to see existing)",
            code=ErrorCode.NOT_FOUND,
        )

    if any(t.id == id for t in manifest.tasks):
        out.fail(
            f"task with id '{id}' already exists",
            code=ErrorCode.EXISTS,
        )

    deps_list = [d.strip() for d in depends_on.split(",") if d.strip()]
    existing_task_ids = {t.id for t in manifest.tasks}
    for dep in deps_list:
        if dep not in existing_task_ids:
            out.fail(
                f"unknown task '{dep}' in --depends-on",
                code=ErrorCode.NOT_FOUND,
            )

    new_task = Task(
        id=id,
        milestone=target_milestone_id,
        title=title,
        description=description,
        depends_on=deps_list,
    )
    # Validate the would-be DAG. If we're auto-creating the implicit 'default'
    # milestone, include it in the candidate so the DAG check doesn't reject the
    # new task for referencing an unknown milestone.
    candidate_milestones = list(manifest.milestones)
    if target_milestone_id == "default" and not any(
        m.id == "default" for m in candidate_milestones
    ):
        candidate_milestones.append(Milestone(id="default", title="Tasks"))
    candidate_manifest = type(manifest)(
        milestones=candidate_milestones, tasks=manifest.tasks + [new_task]
    )
    try:
        validate_dag(candidate_manifest)
    except GraphError as e:
        out.fail(f"invalid task graph: {e}", code=ErrorCode.INVALID_STATE)

    if dry_run:
        log = OpLog()
        log.modify_file(scope.milestones_manifest_path)
        out.info(log.format_summary())
        return

    try:
        with hook_event(
            "task.create",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "title": title, "milestone": target_milestone_id, "description": description},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                if target_milestone_id == "default" and not any(
                    m.id == "default" for m in manifest.milestones
                ):
                    manifest.milestones.append(Milestone(id="default", title="Tasks"))
                manifest.tasks.append(new_task)
    except HookAborted as e:
        out.fail(
            f"task.create aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None:

        def _push():
            ticket = provider.create_task(new_task, scope)
            with edit_milestones(scope) as manifest:
                saved = find_task(manifest, id)
                if saved is not None:
                    saved.tickets[provider.name] = ticket.id

        safe_push(out, "create_task", _push)

    out.result(new_task.model_dump(), human_text=f"Task created: {id}")
