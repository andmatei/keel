"""`keel ai show-config` — parse and display [extensions.ai] configuration."""

from __future__ import annotations

import typer
from pydantic import ValidationError

from keel.ai.config import parse_ai_config, resolve_triggers
from keel.api import ErrorCode, Output, load_project_manifest, resolve_cli_scope


def cmd_show_config(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON to stdout."),
) -> None:
    """Show the validated [extensions.ai] configuration for a project."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, None, out=out)
    pm = load_project_manifest(scope.manifest_path)
    raw = pm.extensions.get("ai", {})

    try:
        config = parse_ai_config(raw)
    except ValidationError as e:
        out.fail(
            f"invalid [extensions.ai] config: {e}",
            code=ErrorCode.INVALID,
        )

    lifecycle = pm.project.lifecycle
    resolved = resolve_triggers(config, lifecycle)

    payload = config.model_dump(by_alias=True)
    payload["lifecycle"] = lifecycle
    payload["resolved_triggers"] = {
        name: t.model_dump(by_alias=True) for name, t in resolved.items()
    }

    if json_mode:
        out.result(payload)
        return

    lines = [f"AI extension: {'enabled' if config.enabled else 'disabled'}"]
    lines.append(f"Lifecycle: {lifecycle}")
    if resolved:
        lines.append(f"Effective triggers: {len(resolved)}")
        for name, trigger in resolved.items():
            source = " (default)" if name not in config.triggers else ""
            lines.append(f"  {name}: {trigger.event} → {trigger.action}{source}")
    else:
        lines.append("Effective triggers: none")
    out.result(payload, human_text="\n".join(lines))
