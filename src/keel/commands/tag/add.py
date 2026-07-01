"""`keel tag add <tag> [<tag>...]`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Output,
    load_project_manifest,
    resolve_cli_scope,
    save_project_manifest,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("tag.add")
def cmd_add(
    ctx: typer.Context,
    tags: list[str] = typer.Argument(..., help="Tags to add (repeatable)."),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Deliverable name (requires --project or CWD detection)."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip tag.add.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Add one or more tags to a project or deliverable."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    manifest_path = scope.manifest_path
    manifest = load_project_manifest(manifest_path)
    current_tags = list(manifest.project.tags)

    # Validate tags up front via the model validator.
    from keel.manifest.models import ProjectMeta

    try:
        ProjectMeta.model_validate(
            {**manifest.project.model_dump(), "tags": current_tags + list(tags)}
        )
    except Exception as e:
        out.fail(f"invalid tag: {e}", code=ErrorCode.VALIDATION)

    try:
        with hook_event(
            "tag.add",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"tags_to_add": list(tags), "current_tags": current_tags},
            positional_args=tuple(tags),
            out=out,
            no_verify=no_verify,
        ) as ev:
            existing = set(manifest.project.tags)
            new_tags = [t.lower().strip() for t in tags if t.lower().strip() not in existing]
            manifest.project.tags = list(manifest.project.tags) + new_tags
            save_project_manifest(manifest_path, manifest)
            ev.add_post_payload(
                {
                    "tags_added": new_tags,
                    "current_tags": list(manifest.project.tags),
                }
            )
    except HookAborted as e:
        out.fail(
            f"tag.add aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"tags": list(manifest.project.tags), "added": new_tags},
        human_text=f"Tags: {', '.join(manifest.project.tags)}"
        if manifest.project.tags
        else "No tags.",
    )
