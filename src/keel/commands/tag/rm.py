"""`keel tag rm <tag> [<tag>...]`."""

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


@hookable("tag.rm")
def cmd_rm(
    ctx: typer.Context,
    tags: list[str] = typer.Argument(..., help="Tags to remove (repeatable)."),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Deliverable name (requires --project or CWD detection)."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip tag.rm.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove one or more tags from a project or deliverable."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    manifest_path = scope.manifest_path
    manifest = load_project_manifest(manifest_path)
    current_tags = list(manifest.project.tags)

    tags_lower = [t.lower().strip() for t in tags]
    existing_set = set(manifest.project.tags)
    not_present = [t for t in tags_lower if t not in existing_set]
    if not_present:
        out.info(f"Tags not present (skipped): {', '.join(not_present)}")

    try:
        with hook_event(
            "tag.rm",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"tags_to_remove": tags_lower, "current_tags": current_tags},
            positional_args=tuple(tags_lower),
            out=out,
            no_verify=no_verify,
        ) as ev:
            to_remove = set(tags_lower)
            actually_removed = [t for t in manifest.project.tags if t in to_remove]
            manifest.project.tags = [t for t in manifest.project.tags if t not in to_remove]
            save_project_manifest(manifest_path, manifest)
            ev.add_post_payload(
                {
                    "tags_removed": actually_removed,
                    "current_tags": list(manifest.project.tags),
                }
            )
    except HookAborted as e:
        out.fail(
            f"tag.rm aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"tags": list(manifest.project.tags), "removed": actually_removed},
        human_text=f"Tags: {', '.join(manifest.project.tags)}"
        if manifest.project.tags
        else "No tags.",
    )
