"""`keel show`."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from keel import workspace
from keel.api import (
    MilestonesManifest,
    Output,
    load_milestones_manifest,
    load_project_manifest,
    ready_tasks,
    resolve_cli_scope,
)
from keel.tags import format_tags


def _has_only_implicit_default(manifest: MilestonesManifest) -> bool:
    return len(manifest.milestones) == 1 and manifest.milestones[0].id == "default"


def cmd_show(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None, help="Project name. Auto-detected from CWD if omitted."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
    brief: bool = typer.Option(False, "--brief", help="Skip milestone/task summary."),
) -> None:
    """Show a project's structure and current state."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(name, None, allow_deliverable=False, out=out)
    name = scope.project

    proj = workspace.project_dir(name)

    m = load_project_manifest(scope.manifest_path)
    phase = workspace.read_phase(scope.unit_dir)
    decisions = sorted(scope.decisions_dir.glob("*.md"))
    decision_count = len(decisions)

    deliverables: list[tuple[str, str]] = []
    d_dir = proj / "deliverables"
    if d_dir.is_dir():
        for d in sorted(d_dir.iterdir()):
            d_manifest = d / "project.toml"
            if d_manifest.is_file():
                d_phase = workspace.read_phase(d)
                deliverables.append((d.name, d_phase))

    # Load milestones if not in brief mode
    milestones_data: dict | None = None
    milestones_manifest: MilestonesManifest | None = None
    if not brief:
        milestones_manifest = load_milestones_manifest(scope.milestones_manifest_path)
        if milestones_manifest.milestones or milestones_manifest.tasks:
            # Count milestones by status
            status_counts = {
                "planned": 0,
                "active": 0,
                "done": 0,
                "cancelled": 0,
            }
            for milestone in milestones_manifest.milestones:
                status_counts[milestone.status] += 1

            # Get active tasks
            active_tasks_list = [t for t in milestones_manifest.tasks if t.status == "active"]

            # Get top 3 ready tasks
            ready = ready_tasks(milestones_manifest)[:3]

            milestones_data = {
                "by_status": status_counts,
                "active_tasks": [
                    {
                        "id": t.id,
                        "milestone": t.milestone,
                        "title": t.title,
                        "branch": t.branch,
                    }
                    for t in active_tasks_list
                ],
                "ready_next": [
                    {
                        "id": t.id,
                        "milestone": t.milestone,
                        "title": t.title,
                        "branch": t.branch,
                    }
                    for t in ready
                ],
            }

    if json_mode:
        result_dict = {
            "name": m.project.name,
            "description": m.project.description,
            "path": str(proj),
            "phase": phase,
            "tags": list(m.project.tags),
            "repos": [r.model_dump() for r in m.repos],
            "decision_count": decision_count,
            "deliverables": [{"name": n, "phase": p} for n, p in deliverables],
        }
        if milestones_data is not None:
            result_dict["milestones"] = milestones_data
        out.result(result_dict)
        return

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("Name", m.project.name)
    table.add_row("Description", m.project.description)
    table.add_row("Path", str(proj))
    table.add_row("Phase", phase)
    if m.project.tags:
        table.add_row("Tags", format_tags(m.project.tags))
    table.add_row("Decisions", str(decision_count))
    if m.repos:
        table.add_row("Repos", "\n".join(f"{r.worktree}/  ←  {r.remote}" for r in m.repos))
    if deliverables:
        table.add_row("Deliverables", "\n".join(f"{n}  [{p}]" for n, p in deliverables))

    # Add milestones section if data is available
    if milestones_data is not None and milestones_manifest is not None:
        single_default = _has_only_implicit_default(milestones_manifest)

        if single_default:
            # Render task-level status counts directly; the milestone is implicit.
            task_status_counts = {
                "planned": 0,
                "active": 0,
                "done": 0,
                "cancelled": 0,
            }
            for t in milestones_manifest.tasks:
                task_status_counts[t.status] += 1
            status_line = "  ".join(f"{k}={v}" for k, v in task_status_counts.items())
            table.add_row("Tasks", status_line)
        else:
            by_status = milestones_data["by_status"]
            status_line = "  ".join(f"{k}={v}" for k, v in by_status.items())
            # Include milestone titles so explicit milestones surface their names.
            milestone_lines = [f"  - {ms.id}: {ms.title}" for ms in milestones_manifest.milestones]
            milestones_text = status_line
            if milestone_lines:
                milestones_text += "\n" + "\n".join(milestone_lines)
            table.add_row("Milestones", milestones_text)

        if milestones_data["active_tasks"]:
            if single_default:
                active_text = "\n".join(
                    f"  - {t['id']} — {t['title']}" for t in milestones_data["active_tasks"]
                )
            else:
                active_text = "\n".join(
                    f"  - {t['id']} ({t['milestone']}) — {t['title']}"
                    for t in milestones_data["active_tasks"]
                )
            table.add_row("Active tasks", active_text)

        if milestones_data["ready_next"]:
            if single_default:
                ready_text = "\n".join(
                    f"  - {t['id']} — {t['title']}" for t in milestones_data["ready_next"]
                )
            else:
                ready_text = "\n".join(
                    f"  - {t['id']} ({t['milestone']}) — {t['title']}"
                    for t in milestones_data["ready_next"]
                )
            table.add_row("Ready next", ready_text)

    out.print_rich(Panel(table, title=f"Project: {m.project.name}", border_style="blue"))
