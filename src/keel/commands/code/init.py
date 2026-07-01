"""`keel code init`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from keel import git, workspace
from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    load_project_manifest,
)


def cmd_init(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Init worktrees declared at deliverable scope."
    ),
    clone_missing: bool = typer.Option(
        False, "--clone-missing", help="Clone any source repo whose local_hint is missing on disk."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip interactive prompts."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Materialize worktrees declared in the manifest. Idempotent."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    unit_dir = scope.unit_dir
    m = load_project_manifest(scope.manifest_path)

    if dry_run:
        log = OpLog()
        for r in m.repos:
            wt = unit_dir / r.worktree
            if not wt.is_dir():
                source = Path(r.local_hint).expanduser() if r.local_hint else Path(r.remote)
                log.create_worktree(wt, source=source, branch=r.branch_prefix or "main")
        out.info(log.format_summary())
        return

    created: list[str] = []
    for r in m.repos:
        wt = unit_dir / r.worktree
        if wt.is_dir():
            continue  # idempotent — already there

        # Resolve source repo on disk
        source: Path | None = None
        if r.local_hint:
            candidate = Path(r.local_hint).expanduser()
            if git.is_git_repo(candidate):
                source = candidate
        if source is None:
            if clone_missing and r.local_hint:
                target = Path(r.local_hint).expanduser()
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(
                        ["git", "clone", r.remote, str(target)],
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    out.fail(
                        f"clone failed for {r.remote}: {e.stderr.decode()}",
                        code=ErrorCode.CLONE_FAILED,
                    )
                source = target
            else:
                out.fail(
                    f"source repo missing: {r.local_hint or r.remote}. "
                    f"Pass --clone-missing to clone it, or set local_hint to a valid path.",
                    code=ErrorCode.SOURCE_MISSING,
                )

        try:
            git.create_worktree(source, wt, branch=r.branch_prefix or "main")
            created.append(str(wt))
        except git.GitError as e:
            out.fail(f"worktree creation failed: {e}", code=ErrorCode.GIT_FAILED)

    out.info(f"Initialized {len(created)} worktree(s).")
    out.result(
        {"created": created, "scope": "deliverable" if deliverable else "project"},
        human_text=f"Initialized {len(created)} worktree(s) for {project}{'/' + deliverable if deliverable else ''}.",
    )
