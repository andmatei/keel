"""`keel daemon list` — show all registered daemons and their status."""

from __future__ import annotations

from pathlib import Path

import typer
from keel.api import Output
from rich.table import Table

from keel_daemon.loader import load_daemons
from keel_daemon.process import is_running


def cmd_list(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show all registered daemons and their current status."""
    out = Output.from_context(ctx, json_mode=json_mode)
    workspace_dir = Path.cwd()

    daemons = load_daemons()

    if not daemons:
        if json_mode:
            out.result({"daemons": []})
        else:
            typer.echo("(no daemons registered)")
        return

    rows = [
        {
            "id": daemon_id,
            "status": "running" if is_running(daemon_id, workspace_dir) else "stopped",
            "interval": daemon_cls.interval,
        }
        for daemon_id, daemon_cls in daemons.items()
    ]

    if json_mode:
        out.result({"daemons": rows})
        return

    table = Table()
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Interval (s)")
    for row in rows:
        table.add_row(row["id"], row["status"], str(row["interval"]))
    out.print_rich(table)
