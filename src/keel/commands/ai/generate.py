"""`keel ai generate` — generate AGENTS.md + CLAUDE.md from project state."""

from __future__ import annotations

from pathlib import Path

import typer

from keel.ai.generate import CLAUDE_MD_POINTER, generate_agents_md
from keel.api import Output, resolve_cli_scope


def cmd_generate(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD."
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Directory to write AGENTS.md and CLAUDE.md into.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON to stdout."),
) -> None:
    """Generate AGENTS.md (and CLAUDE.md pointer) from project state and AI config."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, None, out=out)
    content = generate_agents_md(scope)

    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "AGENTS.md").write_text(content)
        (output / "CLAUDE.md").write_text(CLAUDE_MD_POINTER)

    if json_mode:
        payload: dict[str, str] = {"content": content}
        if output is not None:
            payload["path"] = str(output)
        out.result(payload)
    elif output is not None:
        out.result(None, human_text=f"Wrote AGENTS.md and CLAUDE.md to {output}")
    else:
        out.result(None, human_text=content)
