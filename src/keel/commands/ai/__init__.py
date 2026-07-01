"""`keel ai ...` command group."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="ai",
    help="AI extension commands (config, AGENTS.md generation).",
    no_args_is_help=True,
)

from keel.commands.ai.show_config import cmd_show_config  # noqa: E402

app.command(name="show-config")(cmd_show_config)

from keel.commands.ai.generate import cmd_generate  # noqa: E402

app.command(name="generate")(cmd_generate)
