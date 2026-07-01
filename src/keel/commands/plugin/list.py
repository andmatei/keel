"""`keel plugin list` — enumerate installed keel plugins."""

from __future__ import annotations

from importlib.metadata import entry_points

import typer
from rich.table import Table

from keel.api import Output

GROUPS = [
    "keel.commands",
    "keel.ticket_providers",
    "keel.event_listeners",
    "keel.lifecycles",
    "keel.daemons",
]


def cmd_list(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """List installed plugins across all keel entry-point groups."""
    out = Output.from_context(ctx, json_mode=json_mode)

    rows: list[dict[str, str]] = []
    for group in GROUPS:
        for ep in entry_points(group=group):
            rows.append({"group": group, "name": ep.name, "value": ep.value})

    if json_mode:
        out.result({"plugins": rows})
        return

    if not rows:
        out.result(None, human_text="(no plugins installed)")
        return

    table = Table()
    table.add_column("Group")
    table.add_column("Name")
    table.add_column("Module")
    for r in rows:
        table.add_row(r["group"], r["name"], r["value"])
    out.print_rich(table)
