"""`keel daemon stop <id>` — stop a daemon gracefully."""

from __future__ import annotations

from pathlib import Path

import typer
from keel.api import Output

from keel_daemon.loader import load_daemons
from keel_daemon.process import is_running, stop_daemon


def cmd_stop(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Daemon ID to stop."),
) -> None:
    """Stop a running daemon gracefully."""
    out = Output.from_context(ctx)
    workspace_dir = Path.cwd()

    daemons = load_daemons()
    if id not in daemons:
        out.fail(f"no daemon '{id}' registered")

    if not is_running(id, workspace_dir):
        out.info(f"Daemon '{id}' is not running")
        return

    stop_daemon(id, workspace_dir)
    out.info(f"Daemon '{id}' stopped")
