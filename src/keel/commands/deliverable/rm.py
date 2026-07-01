"""`keel deliverable rm <name>`."""

from __future__ import annotations

import shutil

import typer

from keel import git, workspace
from keel.api import (
    HINT_LIST_DELIVERABLES,
    ErrorCode,
    OpLog,
    Output,
    confirm_destructive,
    resolve_cli_scope,
)
from keel.hooks import HookAborted, hook_event, hookable
from keel.markdown_edit import remove_bullet_under_heading


@hookable("deliverable.rm")
def cmd_rm(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    keep_code: bool = typer.Option(
        False, "--keep-code", help="Preserve the worktree dir even when removing the deliverable."
    ),
    keep_design: bool = typer.Option(
        False,
        "--keep-design",
        help="Preserve the design dir (rare; use to keep records of a removed deliverable).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Allow removal even if the worktree has uncommitted changes."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip interactive prompts (description, etc.)."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip deliverable.rm.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Remove a deliverable, including its design dir, worktree, and parent references."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, None, allow_deliverable=False, out=out)
    project = scope.project
    if not workspace.deliverable_exists(project, name):
        out.fail(
            f"deliverable not found: {project}/{name}\n  {HINT_LIST_DELIVERABLES}",
            code=ErrorCode.NOT_FOUND,
        )

    deliv_scope = workspace.Scope(project=project, deliverable=name)
    deliv = deliv_scope.unit_dir

    if dry_run:
        log = OpLog()
        if not keep_design:
            log.delete_file(deliv)
        log.modify_file(
            scope.design_md_path,
            diff=f"- - **{name}**: ...",
        )
        out.info(log.format_summary())
        return

    confirm_destructive(
        f"Remove deliverable {project}/{name}? This deletes its unit dir.",
        yes=yes,
    )

    try:
        with hook_event(
            "deliverable.rm",
            project=project,
            deliverable=name,
            payload={"name": name, "project": project},
            positional_args=(name,),
            out=out,
            no_verify=no_verify,
        ):
            # Remove worktree if present (and not --keep-code)
            code_dir = deliv / "code"
            if code_dir.is_dir() and not keep_code:
                try:
                    git.remove_worktree(code_dir, force=force)
                except git.GitError as e:
                    out.fail(
                        f"failed to remove worktree at {code_dir}: {e}",
                        code=ErrorCode.GIT_FAILED,
                    )

            # Remove unit contents (unless --keep-design preserves design artifacts).
            # New layout has design files at the unit root rather than a design/ subdir,
            # so we remove everything except the worktree dir(s) we want to keep.
            if not keep_design and deliv.is_dir():
                for child in list(deliv.iterdir()):
                    # Preserve any worktree dirs requested via --keep-code
                    if keep_code and child.name == "code":
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()

            # If the deliverable dir is now empty (no code/ kept), rmdir it.
            try:
                if deliv.is_dir() and not any(deliv.iterdir()):
                    deliv.rmdir()
            except OSError:
                pass  # best-effort

            # Clean up parent design.md (the AST edit is idempotent).
            parent_design = scope.design_md_path
            if parent_design.is_file():
                parent_design.write_text(
                    remove_bullet_under_heading(
                        parent_design.read_text(), "Deliverables", f"- **{name}**:"
                    )
                )
    except HookAborted as e:
        out.fail(
            f"deliverable.rm aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"removed": name, "path": str(deliv)},
        human_text=f"Deliverable removed: {deliv}",
    )
