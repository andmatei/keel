"""`keel code status`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.table import Table

from keel import git, workspace
from keel.api import Output, load_project_manifest


@dataclass
class _RepoStatus:
    remote: str
    local_hint: str | None
    worktree: str
    branch_prefix: str | None
    cloned: bool
    worktree_exists: bool
    branch: str | None
    dirty: bool | None


def _collect_status(unit_dir: Path, repos) -> list[_RepoStatus]:
    rows: list[_RepoStatus] = []
    for r in repos:
        cloned = bool(
            r.local_hint
            and Path(r.local_hint).expanduser().is_dir()
            and git.is_git_repo(Path(r.local_hint).expanduser())
        )
        wt_path = unit_dir / r.worktree
        worktree_exists = wt_path.is_dir() and git.is_git_repo(wt_path)
        branch = git.current_branch(wt_path) if worktree_exists else None
        dirty = git.is_worktree_dirty(wt_path) if worktree_exists else None
        rows.append(
            _RepoStatus(
                remote=r.remote,
                local_hint=r.local_hint,
                worktree=r.worktree,
                branch_prefix=r.branch_prefix,
                cloned=cloned,
                worktree_exists=worktree_exists,
                branch=branch,
                dirty=dirty,
            )
        )
    return rows


def cmd_status(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    deliverable: str | None = typer.Option(
        None, "-D", "--deliverable", help="Status for this deliverable's repos."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Show per-repo worktree status (cloned, exists, branch, clean/dirty)."""
    out = Output.from_context(ctx, json_mode=json_mode)
    scope = workspace.resolve_cli_scope(project, deliverable, out=out)
    project = scope.project
    deliverable = scope.deliverable

    unit_dir = scope.unit_dir
    m = load_project_manifest(scope.manifest_path)

    rows = _collect_status(unit_dir, m.repos)

    if json_mode:
        out.result(
            {
                "repos": [
                    {
                        "remote": r.remote,
                        "worktree": r.worktree,
                        "branch_prefix": r.branch_prefix,
                        "local_hint": r.local_hint,
                        "cloned": r.cloned,
                        "worktree_exists": r.worktree_exists,
                        "branch": r.branch,
                        "dirty": r.dirty,
                    }
                    for r in rows
                ]
            }
        )
        return

    if not rows:
        out.result(None, human_text="(no repos)")
        return

    table = Table()
    table.add_column("Remote")
    table.add_column("Worktree")
    table.add_column("Cloned")
    table.add_column("Worktree exists")
    table.add_column("Branch")
    table.add_column("Dirty")
    for r in rows:
        table.add_row(
            r.remote,
            r.worktree,
            "yes" if r.cloned else "no",
            "yes" if r.worktree_exists else "no",
            r.branch or "-",
            "yes" if r.dirty else ("no" if r.dirty is False else "-"),
        )
    out.print_rich(table)
