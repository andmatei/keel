"""`keel daemon start <id>` — start a daemon in the background."""

from __future__ import annotations

from pathlib import Path

import typer
from keel.api import Output

from keel_daemon.loader import load_daemons
from keel_daemon.process import is_running, start_daemon


def cmd_start(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Daemon ID to start."),
) -> None:
    """Start a daemon in the background."""
    out = Output.from_context(ctx)
    workspace_dir = Path.cwd()

    daemons = load_daemons()
    if id not in daemons:
        out.fail(f"no daemon '{id}' registered")

    if is_running(id, workspace_dir):
        out.info(f"Daemon '{id}' is already running")
        return

    pid = start_daemon(id, workspace_dir)
    out.info(f"Daemon '{id}' started (pid: {pid})")
