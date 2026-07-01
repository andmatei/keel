"""CLI registration for keel-daemon."""

from __future__ import annotations

import typer

from keel_daemon.commands import app as daemon_app


def register(main_app: typer.Typer) -> None:
    """Register the `keel daemon` subcommand group on keel's main app."""
    main_app.add_typer(daemon_app, name="daemon")
