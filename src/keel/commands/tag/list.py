"""`keel tag list` — scoped or global tag listing."""

from __future__ import annotations

from collections import defaultdict

import typer
from rich.tree import Tree

from keel import workspace
from keel.api import Output, load_project_manifest
from keel.tags import format_tags, tag_color


def _scan_global() -> dict[str, dict[str, list]]:
    """Scan all projects and deliverables, returning {tag: {projects: [...], deliverables: [...]}}."""
    tag_map: dict[str, dict[str, list]] = defaultdict(lambda: {"projects": [], "deliverables": []})
    projects_root = workspace.projects_dir()
    if not projects_root.exists():
        return dict(tag_map)
    for child in sorted(projects_root.iterdir()):
        manifest_path = child / "project.toml"
        if not manifest_path.is_file():
            continue
        m = load_project_manifest(manifest_path)
        for tag in m.project.tags:
            tag_map[tag]["projects"].append(m.project.name)
        deliv_dir = child / "deliverables"
        if deliv_dir.is_dir():
            for d in sorted(deliv_dir.iterdir()):
                d_manifest = d / "project.toml"
                if not d_manifest.is_file():
                    continue
                dm = load_project_manifest(d_manifest)
                for tag in dm.project.tags:
                    tag_map[tag]["deliverables"].append(
                        {"project": m.project.name, "name": dm.project.name}
                    )
    return dict(tag_map)


def cmd_list(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Omit for global tag listing."
    ),
    deliverable: str | None = typer.Option(None, "--deliverable", help="Deliverable name."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List tags — scoped to a unit, or globally across all projects."""
    out = Output.from_context(ctx, json_mode=json_mode)

    # Try scoped mode: if --project given, or CWD inside a project.
    scope = None
    if project is not None:
        scope = workspace.resolve_cli_scope(project, deliverable, out=out)
    else:
        detected = workspace.detect_scope()
        if detected.project is not None:
            scope = detected

    if scope is not None:
        _list_scoped(scope, out, json_mode)
    else:
        _list_global(out, json_mode)


def _list_scoped(scope: workspace.Scope, out: Output, json_mode: bool) -> None:
    manifest = load_project_manifest(scope.manifest_path)
    tags = list(manifest.project.tags)

    if json_mode:
        out.result({"tags": tags})
        return

    if not tags:
        out.result(None, human_text="(no tags)")
        return

    out.result(None, human_text=f"Tags: {format_tags(tags)}")


def _list_global(out: Output, json_mode: bool) -> None:
    tag_map = _scan_global()

    if json_mode:
        out.result({"tags": tag_map})
        return

    if not tag_map:
        out.result(None, human_text="(no tags across any project)")
        return

    tree = Tree("Tags")
    for tag in sorted(tag_map):
        data = tag_map[tag]
        n_proj = len(data["projects"])
        n_deliv = len(data["deliverables"])
        parts = []
        if n_proj:
            parts.append(f"{n_proj} project{'s' if n_proj != 1 else ''}")
        if n_deliv:
            parts.append(f"{n_deliv} deliverable{'s' if n_deliv != 1 else ''}")
        color = tag_color(tag)
        branch = tree.add(f"[{color}]{tag}[/{color}] ({', '.join(parts)})")
        for name in sorted(data["projects"]):
            branch.add(name)
        for d in sorted(data["deliverables"], key=lambda x: (x["project"], x["name"])):
            branch.add(f"{d['project']} / {d['name']}")

    out.print_rich(tree)
