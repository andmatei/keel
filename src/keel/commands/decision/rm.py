"""`keel decision rm <slug>`."""

from __future__ import annotations

import typer

from keel.api import (
    HINT_LIST_DECISIONS,
    ErrorCode,
    OpLog,
    Output,
    confirm_destructive,
    resolve_cli_scope,
)
from keel.commands.decision.show import _find_decision


def cmd_rm(
    ctx: typer.Context,
    slug: str = typer.Argument(..., help="Decision slug (date prefix optional) or full filename."),
    deliverable: str | None = typer.Option(
        None,
        "-D",
        "--deliverable",
        help="Decision scope: a deliverable instead of the project. Auto-detected from CWD.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip interactive prompts (description, etc.)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a decision file (the typical 'changed my mind' pattern is `decision new --supersedes` instead)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    target_dir = scope.decisions_dir

    path = _find_decision(target_dir, slug)
    if path is None:
        out.fail(f"decision not found: {slug}\n  {HINT_LIST_DECISIONS}", code=ErrorCode.NOT_FOUND)

    if dry_run:
        log = OpLog()
        log.delete_file(path)
        out.info(log.format_summary())
        return

    confirm_destructive(f"Remove decision {path.name}?", yes=yes)

    path.unlink()
    out.result(
        {"removed": path.stem, "path": str(path)},
        human_text=f"Decision removed: {path}",
    )
