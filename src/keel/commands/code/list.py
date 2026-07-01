"""`keel code list`."""

from __future__ import annotations

import typer
from rich.table import Table

from keel import workspace
from keel.api import Output, load_project_manifest


def cmd_list(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Show repos for this deliverable instead of the project."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List source repos declared in the manifest."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable, out=out)

    m = load_project_manifest(scope.manifest_path)

    repos_data = [
        {
            "remote": r.remote,
            "local_hint": r.local_hint,
            "worktree": r.worktree,
            "branch_prefix": r.branch_prefix,
        }
        for r in m.repos
    ]

    if json_mode:
        out.result({"repos": repos_data})
        return

    if not m.repos:
        out.result(None, human_text="(no repos)")
        return

    table = Table()
    table.add_column("Remote")
    table.add_column("Worktree")
    table.add_column("Branch prefix")
    table.add_column("Local hint")
    for r in m.repos:
        table.add_row(r.remote, r.worktree, r.branch_prefix or "-", r.local_hint or "-")
    out.print_rich(table)
