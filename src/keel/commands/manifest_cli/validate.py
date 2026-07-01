"""`keel manifest validate <path>` — lint a TOML manifest against its schema."""

from __future__ import annotations

from pathlib import Path

import typer

from keel.api import ErrorCode, Output


def cmd_validate(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Path to a project.toml or milestones.toml."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Validate a manifest file against its Pydantic schema."""
    out = Output.from_context(ctx, json_mode=json_mode)

    if not path.is_file():
        out.fail(f"file not found: {path}", code=ErrorCode.NOT_FOUND)

    name = path.name
    if name == "project.toml":
        from keel.manifest import load_project_manifest

        loader = load_project_manifest
        kind = "project"
    elif name == "milestones.toml":
        from functools import partial

        from keel.manifest import load_milestones_manifest

        loader = partial(load_milestones_manifest, validate=True)
        kind = "milestones"
    else:
        out.fail(
            f"unsupported manifest file: {name} (expected project.toml/milestones.toml)",
            code=ErrorCode.INVALID_NAME,
        )

    try:
        loader(path)
    except Exception as e:
        out.fail(f"{kind} manifest invalid: {e}", code=ErrorCode.INVALID_STATE)

    out.result(
        {"path": str(path), "kind": kind, "valid": True},
        human_text=f"OK — {kind} manifest valid: {path}",
    )
