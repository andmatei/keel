"""`keel restore <name>` — bring a project back from .archive/."""

from __future__ import annotations

import typer

from keel.api import ErrorCode, OpLog, Output, confirm_destructive, projects_dir
from keel.hooks import HookAborted, hook_event, hookable


@hookable("project.restore")
def cmd_restore(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Project name to restore from .archive/."),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirm prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print intended operations and exit."),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip project.restore.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Move a project from `<projects-dir>/.archive/` back to the active workspace."""
    out = Output.from_context(ctx, json_mode=json_mode)

    pdir = projects_dir()
    archive_root = pdir / ".archive"
    target_dir = pdir / name

    # Find archived project (may have date suffix like "foo-2026-01-15")
    archive_candidates = list(archive_root.glob(f"{name}-*")) if archive_root.exists() else []

    if not archive_candidates:
        out.fail(
            f"no archived project named '{name}' (looked in {archive_root})",
            code=ErrorCode.NOT_FOUND,
        )

    if len(archive_candidates) > 1:
        out.fail(
            f"multiple archived versions of '{name}' found; restore manually",
            code=ErrorCode.INVALID,
        )

    archive_dir = archive_candidates[0]

    if target_dir.exists():
        out.fail(
            f"cannot restore: {target_dir} already exists",
            code=ErrorCode.EXISTS,
        )

    if dry_run:
        log = OpLog()
        log.modify_file(target_dir)  # Log the rename operation
        out.info(log.format_summary())
        return

    confirm_destructive(f"Restore project '{name}' from archive?", yes=yes)

    try:
        with hook_event(
            "project.restore",
            project=name,
            deliverable=None,
            payload={},
            positional_args=(name,),
            out=out,
            no_verify=no_verify,
        ) as ev:
            archive_dir.rename(target_dir)
            ev.add_post_payload({"path": str(target_dir)})
    except HookAborted as e:
        out.fail(
            f"project.restore aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"restored": name, "path": str(target_dir)},
        human_text=f"Restored: {name} → {target_dir}",
    )
