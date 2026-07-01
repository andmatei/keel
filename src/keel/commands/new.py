"""`keel new <name>`."""

from __future__ import annotations

from pathlib import Path

import typer

from keel import git_ops, workspace
from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    RepoSpec,
    require_or_fail,
    slugify,
)
from keel.commands._helpers import _build_repo_specs, _scaffold_unit
from keel.hooks import HookAborted, hook_event, hookable
from keel.lifecycles import (
    LifecycleNotFoundError,
    load_lifecycle,
)


@hookable("project.create")
def cmd_new(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Project name (will be slugified)."),
    description: str | None = typer.Option(
        None,
        "-d",
        "--description",
        help="Brief project description; required (prompted on TTY if missing).",
    ),
    repos: list[str] | None = typer.Option(
        None,
        "-r",
        "--repo",
        help="Source git repo for a worktree. Repeatable for multi-repo projects.",
    ),
    no_worktree: bool = typer.Option(
        False, "--no-worktree", help="Skip worktree creation even if --repo provided."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip interactive prompts (description, etc.)."
    ),
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip project.create.pre hooks (in-tree + plugin + user-script)."
    ),
    lifecycle: str = typer.Option(
        "default",
        "--lifecycle",
        help="Phase lifecycle to use for this project. See 'keel lifecycle list'.",
    ),
    tags: list[str] | None = typer.Option(
        None,
        "--tag",
        help="Tag for the new project. Repeatable for multiple tags.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Create a new project workspace."""
    out = Output.from_context(ctx, json_mode=json_mode)
    slug = slugify(name)
    if not slug:
        out.fail("invalid project name", code=ErrorCode.INVALID_NAME, exit_code=2)

    scope = workspace.Scope(project=slug, deliverable=None)
    proj = scope.unit_dir
    if proj.exists():
        out.fail(f"project already exists: {proj}", code=ErrorCode.EXISTS)

    description = require_or_fail(description, arg_name="--description", label="Description")

    # Validate and load the lifecycle
    try:
        lc = load_lifecycle(lifecycle)
    except LifecycleNotFoundError:
        out.fail(
            f"unknown lifecycle '{lifecycle}' (run 'keel lifecycle list' to see available options)",
            code=ErrorCode.NOT_FOUND,
        )

    # Resolve and validate repos up front
    repo_paths: list[Path] = []
    if repos and not no_worktree:
        for r in repos:
            rp = Path(r).expanduser().resolve()
            if not git_ops.is_git_repo(rp):
                out.fail(f"not a git repo: {rp}", code=ErrorCode.NOT_A_REPO)
            repo_paths.append(rp)

    # Build repo specs from validated paths.
    repo_specs = _build_repo_specs(slug, repo_paths)

    if dry_run:
        log = OpLog()
        log.create_file(scope.manifest_path, size=0)
        log.create_file(scope.readme_path, size=0)
        log.create_file(scope.scope_md_path, size=0)
        log.create_file(scope.design_md_path, size=0)
        log.create_file(scope.phase_path, size=0)
        log.create_file(scope.lifecycle_lock_path, size=0)
        for rp, spec in zip(repo_paths, repo_specs, strict=True):
            log.create_worktree(proj / spec.worktree, source=rp, branch=spec.branch_prefix)
        out.info(log.format_summary())
        return

    created_worktrees: list[str] = []

    # Fire pre-new, do the work, fire post-new.
    try:
        with hook_event(
            "project.create",
            project=slug,
            payload={"description": description, "lifecycle": lifecycle, "tags": tags or []},
            positional_args=(slug,),
            out=out,
            no_verify=no_verify,
        ) as ev:
            manifest = _scaffold_unit(
                scope=scope,
                name=slug,
                description=description,
                lifecycle=lifecycle,
                repos=repo_specs,
                lc=lc,
                tags=tags or [],
            )

            # Worktrees (last — file ops above already done)
            for rp, spec in zip(repo_paths, manifest.repos, strict=True):
                wt_dest = proj / spec.worktree
                try:
                    git_ops.create_worktree(rp, wt_dest, branch=spec.branch_prefix)
                    created_worktrees.append(str(wt_dest))
                except git_ops.GitError as e:
                    out.info(f"Files are at {proj}; clean up with `rm -rf {proj}` or retry.")
                    out.fail(f"worktree creation failed: {e}", code=ErrorCode.GIT_FAILED)

            ev.add_post_payload({"path": str(proj), "worktrees": created_worktrees})
    except HookAborted as e:
        out.fail(
            f"project.create aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"path": str(proj), "worktrees": created_worktrees},
        human_text=f"Project created: {proj}",
    )