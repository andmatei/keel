"""`keel tag ...` command group."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="tag",
    help="Manage tags on projects and deliverables.",
    no_args_is_help=True,
)

from keel.commands.tag.add import cmd_add  # noqa: E402

app.command(name="add")(cmd_add)

from keel.commands.tag.rm import cmd_rm  # noqa: E402

app.command(name="rm")(cmd_rm)

from keel.commands.tag.list import cmd_list  # noqa: E402

app.command(name="list")(cmd_list)
