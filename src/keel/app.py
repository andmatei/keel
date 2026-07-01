"""Top-level Typer app and global flags."""

from __future__ import annotations

from importlib.metadata import entry_points

import typer

from keel import __version__

app = typer.Typer(
    name="keel",
    help="Manage the ~/projects/ workspace.",
    no_args_is_help=True,
    add_completion=True,
)


# Empty subapp pre-registered so plugins can extend it via entry points.
# Plan 5 will activate this with bundled providers.
ticketing_app = typer.Typer(
    name="ticketing",
    help="Ticketing system integration (Jira, GitHub Issues, etc.). Provided by plugins.",
    no_args_is_help=True,
)
app.add_typer(ticketing_app, name="ticketing")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Suppress info logs."),
) -> None:
    """keel: scope-driven development scaffolder for ~/projects/."""
    ctx.obj = {"quiet": quiet}


def _load_plugin_commands() -> None:
    """Discover and load command-group plugins via the `keel.commands` entry-point group.

    A plugin entry point should resolve to a callable that takes the keel `app`
    (or a subapp like `ticketing_app`) and registers its commands on it. Example:

        # In a plugin's pyproject.toml:
        [project.entry-points."keel.commands"]
        my_cmd = "my_pkg.cli:register"

        # In my_pkg/cli.py:
        def register(app: typer.Typer) -> None:
            app.command(name="my-cmd")(my_cmd_func)

    For ticketing-specific plugins, use `keel.ticket_providers` (Plan 5).
    """
    for ep in entry_points(group="keel.commands"):
        try:
            register = ep.load()
            register(app)
        except Exception as e:  # noqa: BLE001
            # Don't crash the whole CLI if a plugin fails to load.
            typer.echo(
                f"warning: failed to load plugin '{ep.name}': {e}",
                err=True,
            )


# Built-in commands — register first, then load plugins.
from keel.commands.new import cmd_new  # noqa: E402

app.command(name="new")(cmd_new)

from keel.commands.list import cmd_list  # noqa: E402

app.command(name="list")(cmd_list)

from keel.commands.show import cmd_show  # noqa: E402

app.command(name="show")(cmd_show)

from keel.commands.phase import cmd_phase  # noqa: E402

app.command(name="phase")(cmd_phase)

from keel.commands.validate import cmd_validate  # noqa: E402

app.command(name="validate")(cmd_validate)

from keel.commands.archive import cmd_archive  # noqa: E402

app.command(name="archive")(cmd_archive)

from keel.commands.restore import cmd_restore  # noqa: E402

app.command(name="restore")(cmd_restore)

from keel.commands.rename import cmd_rename  # noqa: E402

app.command(name="rename")(cmd_rename)

from keel.commands.completion import cmd_completion  # noqa: E402

app.command(name="completion")(cmd_completion)

from keel.commands.deliverable import app as deliverable_app  # noqa: E402

app.add_typer(deliverable_app, name="deliverable")

from keel.commands.decision import app as decision_app  # noqa: E402

app.add_typer(decision_app, name="decision")

from keel.commands.milestone import app as milestone_app  # noqa: E402

app.add_typer(milestone_app, name="milestone")

from keel.commands.task import app as task_app  # noqa: E402

app.add_typer(task_app, name="task")

from keel.commands.design import app as design_app  # noqa: E402

app.add_typer(design_app, name="design")

from keel.commands.code import app as code_app  # noqa: E402

app.add_typer(code_app, name="code")

from keel.commands.plugin import app as plugin_app  # noqa: E402

app.add_typer(plugin_app, name="plugin")

from keel.commands.manifest_cli import app as manifest_app  # noqa: E402

app.add_typer(manifest_app, name="manifest")

from keel.commands.lifecycle import app as lifecycle_app  # noqa: E402

app.add_typer(lifecycle_app, name="lifecycle")

from keel.commands.hooks import app as hooks_app  # noqa: E402

app.add_typer(hooks_app, name="hooks")

from keel.commands.tag import app as tag_app  # noqa: E402

app.add_typer(tag_app, name="tag")

from keel.commands.ai import app as ai_app  # noqa: E402

app.add_typer(ai_app, name="ai")

# Load any third-party plugins last so they can extend existing groups.
_load_plugin_commands()
