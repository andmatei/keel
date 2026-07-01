"""`keel lifecycle init <name>` — scaffold a new lifecycle TOML in the user library."""

from __future__ import annotations

import typer

from keel import templates
from keel.api import ErrorCode, Output
from keel.util import is_path_component
from keel.workspace import projects_dir


def cmd_init(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Lifecycle name (also the filename stem)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file with this name."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Scaffold `<projects-dir>/.keel/lifecycles/<name>.toml` with placeholder states."""
    out = Output.from_context(ctx, json_mode=json_mode)
    if not is_path_component(name):
        out.fail("invalid lifecycle name", code=ErrorCode.INVALID_NAME, exit_code=2)

    target_dir = projects_dir() / ".keel" / "lifecycles"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{name}.toml"

    if target.exists() and not force:
        out.fail(
            f"{target} already exists (use --force to overwrite)",
            code=ErrorCode.EXISTS,
        )

    target.write_text(templates.render("lifecycle.toml.j2", name=name))
    out.result(
        {"path": str(target), "name": name},
        human_text=f"Scaffolded: {target}",
    )
