"""`keel task show <id>`."""

from __future__ import annotations

import typer

from keel.api import Output, get_task, load_milestones_manifest, resolve_cli_scope


def cmd_show(
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
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show a task's metadata and dependency tree."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    manifest = load_milestones_manifest(scope.milestones_manifest_path)

    task = get_task(manifest, id, out=out)

    by_id = {t.id: t for t in manifest.tasks}
    deps_status = [
        {"id": d, "status": by_id[d].status if d in by_id else "unknown"} for d in task.depends_on
    ]

    payload = {**task.model_dump(), "deps_status": deps_status}

    if json_mode:
        out.result(payload)
        return

    lines = [
        f"Task: {task.id}",
        f"Milestone: {task.milestone}",
        f"Title: {task.title}",
        f"Status: {task.status}",
    ]
    if task.description:
        lines.append(f"Description: {task.description}")
    if task.branch:
        lines.append(f"Branch: {task.branch}")
    if task.tickets:
        for prov, tid in task.tickets.items():
            lines.append(f"Ticket ({prov}): {tid}")
    if deps_status:
        lines.append("Dependencies:")
        for d in deps_status:
            lines.append(f"  - {d['id']} ({d['status']})")

    out.result(payload, human_text="\n".join(lines))
