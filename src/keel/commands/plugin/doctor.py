"""`keel plugin doctor` — validate plugin configuration for the current project."""

from __future__ import annotations

import typer

from keel.api import (
    ErrorCode,
    Output,
    load_project_manifest,
    resolve_cli_scope,
)
from keel.ticketing import get_provider_for_project
from keel.ticketing.registry import list_providers


def cmd_doctor(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project name. Auto-detected from CWD if omitted.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Validate plugin configuration for the current project."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, None, out=out)
    pm = load_project_manifest(scope.manifest_path)

    findings: list[dict[str, str]] = []

    # Check ticketing config
    cfg = pm.extensions.get("ticketing", {})
    if isinstance(cfg, dict) and cfg.get("provider"):
        provider_name = cfg["provider"]
        installed = list_providers()
        if provider_name not in installed:
            findings.append(
                {
                    "level": "error",
                    "area": "ticketing",
                    "message": f"provider '{provider_name}' is configured but not installed (have: {installed or 'none'})",
                }
            )
        else:
            try:
                provider = get_provider_for_project(pm)
                if provider is None:
                    findings.append(
                        {
                            "level": "error",
                            "area": "ticketing",
                            "message": "provider failed to instantiate",
                        }
                    )
            except Exception as e:
                findings.append(
                    {"level": "error", "area": "ticketing", "message": f"configure() raised: {e}"}
                )

    # Check AI config
    ai_raw = pm.extensions.get("ai")
    if ai_raw is not None:
        from pydantic import ValidationError

        from keel.ai.config import parse_ai_config

        try:
            parse_ai_config(ai_raw)
        except ValidationError as e:
            findings.append(
                {
                    "level": "error",
                    "area": "ai",
                    "message": f"invalid [extensions.ai] config: {e}",
                }
            )

    if json_mode:
        out.result({"findings": findings})
    else:
        if not findings:
            out.result(None, human_text="OK — no issues found.")
        else:
            for f in findings:
                out.warn(f"[{f['area']}] {f['message']}")

    if any(f["level"] == "error" for f in findings):
        out.fail("plugin doctor found issues", code=ErrorCode.INVALID_STATE)
