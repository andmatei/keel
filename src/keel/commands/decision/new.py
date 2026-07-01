"""`keel decision new <title>`."""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
from datetime import date
from pathlib import Path

import typer

from keel import templates
from keel.api import HINT_LIST_DECISIONS, ErrorCode, OpLog, Output, resolve_cli_scope, slugify
from keel.hooks import HookAborted, hook_event, hookable
from keel.util import is_path_component


@hookable("decision.create")
def cmd_new(
    ctx: typer.Context,
    title: str = typer.Argument(...),
    deliverable: str | None = typer.Option(
        None,
        "-D",
        "--deliverable",
        help="Decision scope: a deliverable instead of the project. Auto-detected from CWD.",
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    slug: str | None = typer.Option(
        None, "--slug", help="Override the auto-generated slug from the title."
    ),
    supersedes: str | None = typer.Option(
        None,
        "--supersedes",
        help="Mark an existing decision as superseded and link forward to this one. Pass the slug or the full filename.",
    ),
    no_edit: bool = typer.Option(
        False, "--no-edit", help="Don't open $EDITOR after creating the decision file."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing decision file with the same name."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip decision.create.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Create a new decision record at the current scope (project or deliverable)."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    # Compute target dir
    target_dir = scope.decisions_dir
    scope_label = "deliverable" if deliverable else "project"

    today = date.today().isoformat()
    slug_value = slug or slugify(title)
    if not slug_value or not is_path_component(slug_value):
        out.fail("invalid decision slug", code=ErrorCode.INVALID_TITLE, exit_code=2)
    filename = f"{today}-{slug_value}.md"
    path = target_dir / filename

    if path.exists() and not force:
        out.fail(f"decision file already exists: {path}", code=ErrorCode.EXISTS)

    # Validate --supersedes early, before creating the new file
    supersedes_path: Path | None = None
    if supersedes:
        candidate_paths = (
            list(target_dir.glob(f"*-{supersedes}.md"))
            if not supersedes.endswith(".md")
            else [target_dir / supersedes]
        )
        candidate_paths = [c for c in candidate_paths if c.is_file()]
        if not candidate_paths:
            out.fail(
                f"--supersedes: no decision matching '{supersedes}' found in {target_dir}\n  {HINT_LIST_DECISIONS}",
                code=ErrorCode.NOT_FOUND,
            )
        supersedes_path = candidate_paths[0]

    if dry_run:
        log = OpLog()
        log.create_file(path, size=0)
        out.info(log.format_summary())
        return

    try:
        with hook_event(
            "decision.create",
            project=project,
            deliverable=deliverable,
            payload={"slug": slug_value, "title": title, "supersedes": supersedes},
            positional_args=(slug_value,),
            out=out,
            no_verify=no_verify,
        ) as ev:
            target_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(templates.render("decision_entry.j2", date=today, title=title))

            if supersedes and supersedes_path is not None:
                # supersedes_path was validated above — apply the status mutation
                old_text = supersedes_path.read_text()
                # Replace status field in frontmatter
                new_text = re.sub(
                    r"^status:\s*\S+",
                    "status: superseded",
                    old_text,
                    count=1,
                    flags=re.MULTILINE,
                )
                # Append "Superseded by:" line at end
                superseded_by_line = f"\nSuperseded by: {filename[:-3]}\n"  # strip .md
                if "Superseded by:" not in new_text:
                    new_text = new_text.rstrip("\n") + superseded_by_line
                supersedes_path.write_text(new_text)

            ev.add_post_payload({"path": str(path)})
    except HookAborted as e:
        out.fail(
            f"decision.create aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"path": str(path), "scope": scope_label, "slug": slug_value, "supersedes": supersedes},
        human_text=f"Decision created: {path}",
    )

    # Open editor
    if not no_edit and os.environ.get("EDITOR") and not dry_run:
        with contextlib.suppress(Exception):
            subprocess.run([os.environ["EDITOR"], str(path)], check=False)
