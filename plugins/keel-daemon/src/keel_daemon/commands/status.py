"""`keel daemon status <id>` — show daemon status."""

from __future__ import annotations

from pathlib import Path

import typer
from keel.api import Output

from keel_daemon.loader import load_daemons
from keel_daemon.process import is_running, read_recent_logs


def cmd_status(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Daemon ID to inspect."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show the current status of a daemon."""
    out = Output.from_context(ctx, json_mode=json_mode)
    workspace_dir = Path.cwd()

    daemons = load_daemons()
    if id not in daemons:
        out.fail(f"no daemon '{id}' registered")

    running = is_running(id, workspace_dir)
    lines = read_recent_logs(id, workspace_dir, n=5)
    data = {
        "id": id,
        "status": "running" if running else "stopped",
        "recent_logs": lines,
    }

    if json_mode:
        out.result(data)
        return

    typer.echo(f"Daemon '{id}' is {'running' if running else 'stopped'}")
    if lines:
        typer.echo(lines[-1].rstrip())
