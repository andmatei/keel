"""`keel milestone add <id> --title "..."`."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Milestone,
    OpLog,
    Output,
    edit_milestones,
    find_milestone,
    resolve_cli_scope,
    safe_push,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


@hookable("milestone.create")
def cmd_add(
    ctx: typer.Context,
    id: str = typer.Argument(..., help="Milestone identifier (e.g., 'm1', 'foundation')."),
    title: str = typer.Option(..., "--title", help="Human-readable milestone title."),
    description: str | None = typer.Option(None, "--description", help="Optional description."),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Scope: a deliverable."
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD."
    ),
    no_push: bool = typer.Option(
        False,
        "--no-push",
        help="Skip pushing to the configured ticketing provider for this invocation.",
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip milestone.create.pre hooks."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit."),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON to stdout."),
) -> None:
    """Create a new milestone in the current scope's `milestones.toml`."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)

    new_milestone = Milestone(id=id, title=title, description=description)

    if dry_run:
        log = OpLog()
        path = scope.milestones_manifest_path
        log.create_file(path, size=0) if not path.exists() else None
        log.modify_file(path)
        out.info(log.format_summary())
        return

    try:
        with hook_event(
            "milestone.create",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "title": title, "description": description, "parent": new_milestone.parent},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ):
            with edit_milestones(scope) as manifest:
                if any(m.id == id for m in manifest.milestones):
                    out.fail(
                        f"milestone with id '{id}' already exists in {scope.milestones_manifest_path}",
                        code=ErrorCode.EXISTS,
                    )
                manifest.milestones.append(new_milestone)
    except HookAborted as e:
        out.fail(
            f"milestone.create aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    # If ticketing is configured and --no-push wasn't passed, push to the provider.
    provider = with_provider(scope, no_push=no_push)
    if provider is not None:

        def _push():
            ticket = provider.create_milestone(new_milestone, scope)
            with edit_milestones(scope) as manifest:
                saved = find_milestone(manifest, new_milestone.id)
                if saved is not None:
                    saved.tickets[provider.name] = ticket.id

        safe_push(out, "create_milestone", _push)

    payload = new_milestone.model_dump()
    out.result(
        payload,
        human_text=f"Milestone created: {id}",
    )
