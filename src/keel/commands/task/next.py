"""`keel task next` — print the next ready task."""

from __future__ import annotations

import os

import typer

from keel.api import (
    ErrorCode,
    Output,
    edit_milestones,
    get_task,
    load_milestones_manifest,
    ready_tasks,
    resolve_cli_scope,
    slugify,
    topological_sort,
)


def cmd_next(
    ctx: typer.Context,
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
    milestone: str | None = typer.Option(
        None, "--milestone", "-m", help="Limit to one milestone's tasks."
    ),
    start: bool = typer.Option(
        False, "--start", help="Start the next task (planned -> active) and record its branch."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Print the topologically-first ready task; with --start, mark it active."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    manifest = load_milestones_manifest(scope.milestones_manifest_path)

    ready_ids = {t.id for t in ready_tasks(manifest)}
    candidates = [t for t in topological_sort(manifest) if t.id in ready_ids]
    if milestone:
        candidates = [t for t in candidates if t.milestone == milestone]

    if not candidates:
        out.fail("no ready tasks", code=ErrorCode.NOT_FOUND)

    next_task = candidates[0]

    if start:
        # Start the task by updating the manifest directly
        def _default_branch(user: str, project_name: str, milestone_id: str, task_id: str) -> str:
            return f"{slugify(user)}/{project_name}-{milestone_id}-{task_id}"

        with edit_milestones(scope) as manifest:
            task = get_task(manifest, next_task.id, out=out)
            if task.status != "planned":
                out.fail(
                    f"cannot start task in status '{task.status}' (must be 'planned')",
                    code=ErrorCode.INVALID_STATE,
                )
            user = os.environ.get("USER", "user")
            task.branch = _default_branch(user, scope.project, task.milestone, task.id)
            task.status = "active"

        out.result(
            task.model_dump(),
            human_text=f"Started: {next_task.id} (branch: {task.branch})",
        )
        return

    out.result(
        next_task.model_dump(),
        human_text=f"Next: {next_task.id} ({next_task.milestone}) — {next_task.title}",
    )
