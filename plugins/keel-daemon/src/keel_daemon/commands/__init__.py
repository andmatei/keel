"""`keel daemon ...` command group."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="daemon",
    help="Manage long-running background daemons.",
    no_args_is_help=True,
)

from keel_daemon.commands.list import cmd_list  # noqa: E402
from keel_daemon.commands.logs import cmd_logs  # noqa: E402
from keel_daemon.commands.start import cmd_start  # noqa: E402
from keel_daemon.commands.status import cmd_status  # noqa: E402
from keel_daemon.commands.stop import cmd_stop  # noqa: E402

app.command(name="list")(cmd_list)
app.command(name="start")(cmd_start)
app.command(name="stop")(cmd_stop)
app.command(name="status")(cmd_status)
app.command(name="logs")(cmd_logs)
