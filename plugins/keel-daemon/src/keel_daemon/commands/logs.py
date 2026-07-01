"""`keel daemon logs <id>` — print recent log lines."""

from __future__ import annotations

from pathlib import Path

import typer
from keel.api import Output

from keel_daemon.loader import load_daemons
from keel_daemon.process import read_recent_logs


def cmd_logs(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Daemon ID whose logs to show."),
    n: int = typer.Option(20, "-n", "--lines", help="Number of recent log lines to print."),
) -> None:
    """Print recent log lines for a daemon."""
    out = Output.from_context(ctx)
    workspace_dir = Path.cwd()

    daemons = load_daemons()
    if id not in daemons:
        out.fail(f"no daemon '{id}' registered")

    lines = read_recent_logs(id, workspace_dir, n=n)
    if not lines:
        typer.echo("(no logs)")
        return

    for line in lines:
        typer.echo(line.rstrip("\n"))
