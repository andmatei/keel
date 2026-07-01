"""`keel list`."""

from __future__ import annotations

from dataclasses import dataclass

import typer
from rich.tree import Tree

from keel import workspace
from keel.api import Output, load_milestones_manifest, load_project_manifest
from keel.tags import format_tags


@dataclass
class _ProjectRow:
    name: str
    phase: str
    description: str
    deliverable_count: int
    active_milestones: int
    active_tasks: int
    tags: list[str]


def _scan(projects_root) -> list[_ProjectRow]:
    rows: list[_ProjectRow] = []
    if not projects_root.exists():
        return rows
    for child in sorted(projects_root.iterdir()):
        manifest = child / "project.toml"
        if not manifest.is_file():
            continue
        m = load_project_manifest(manifest)
        phase = workspace.read_phase(child)
        d_dir = child / "deliverables"
        d_count = 0
        if d_dir.is_dir():
            d_count = sum(1 for d in d_dir.iterdir() if (d / "project.toml").is_file())

        # Load milestones and count active ones
        active_milestones_count = 0
        active_tasks_count = 0
        milestones_file = child / "milestones.toml"
        if milestones_file.is_file():
            try:
                mm = load_milestones_manifest(milestones_file)
                active_milestones_count = sum(1 for m in mm.milestones if m.status == "active")
                active_tasks_count = sum(1 for t in mm.tasks if t.status == "active")
            except Exception:
                # If milestones.toml is malformed, just skip
                pass

        rows.append(
            _ProjectRow(
                name=m.project.name,
                phase=phase,
                description=m.project.description,
                deliverable_count=d_count,
                active_milestones=active_milestones_count,
                active_tasks=active_tasks_count,
                tags=list(m.project.tags),
            )
        )
    return rows


def cmd_list(
    ctx: typer.Context,
    phase: str | None = typer.Option(
        None, "--phase", help="Filter to projects in the given phase."
    ),
    active: bool = typer.Option(
        False, "--active", help="Show only projects with at least one active milestone or task."
    ),
    tag: list[str] | None = typer.Option(
        None, "--tag", help="Filter to projects with this tag. Repeatable; AND semantics."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List projects in the workspace."""
    out = Output.from_context(ctx, json_mode=json_mode)
    rows = _scan(workspace.projects_dir())
    total = len(rows)
    if phase:
        rows = [r for r in rows if r.phase == phase]
    if active:
        rows = [r for r in rows if r.active_milestones > 0 or r.active_tasks > 0]
    if tag:
        tag_set = set(tag)
        rows = [r for r in rows if tag_set.issubset(set(r.tags))]

    if json_mode:
        out.result(
            {
                "projects": [
                    {
                        "name": r.name,
                        "phase": r.phase,
                        "description": r.description,
                        "deliverable_count": r.deliverable_count,
                        "active_milestones": r.active_milestones,
                        "active_tasks": r.active_tasks,
                        "tags": r.tags,
                    }
                    for r in rows
                ]
            }
        )
        return

    if not rows:
        if phase is not None and total > 0:
            out.result(None, human_text=f"(no projects in phase {phase!r})")
        else:
            out.result(None, human_text="(no projects)")
        return

    tree = Tree("Projects")
    for r in rows:
        label = f"[bold]{r.name}[/bold]  \\[{r.phase}]"
        if r.deliverable_count:
            label += (
                f"  ({r.deliverable_count} deliverable{'s' if r.deliverable_count != 1 else ''})"
            )
        # Add active milestones and tasks info
        if r.tags:
            label += f"  {format_tags(r.tags)}"
        if r.active_milestones or r.active_tasks:
            label += f"  [yellow]Active M: {r.active_milestones} T: {r.active_tasks}[/yellow]"
        tree.add(label)
    out.print_rich(tree)
