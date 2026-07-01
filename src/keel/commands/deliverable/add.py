"""`keel deliverable add <name>`."""

from __future__ import annotations

from pathlib import Path

import typer

from keel import git_ops, workspace
from keel.api import (
    ErrorCode,
    OpLog,
    Output,
    ProjectManifest,
    ProjectMeta,
    RepoSpec,
    load_project_manifest,
    require_or_fail,
    resolve_cli_scope,
    save_project_manifest,
    slugify,
)
from keel.hooks import HookAborted, hook_event, hookable
from keel.lifecycles import LifecycleNotFoundError, load_lifecycle
from keel.markdown_edit import insert_under_heading


@hookable("deliverable.create")
def cmd_add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Deliverable name (will be slugified)."),
    description: str | None = typer.Option(
        None, "-d", "--description", help="Brief deliverable description; required."
    ),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    repo: str | None = typer.Option(
        None,
        "-r",
        "--repo",
        help="Source git repo for the deliverable's own worktree. Mutually exclusive with --shared.",
    ),
    shared: bool = typer.Option(
        False, "--shared", help="Use the parent project's worktree (no own [[repos]])."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip interactive prompts (description, etc.)."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip deliverable.create.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Create a new deliverable inside a project.

    Equivalent to creating a nested project — writes the same `project.toml`
    schema and `.keel/` state as `keel new`.
    """
    out = Output.from_context(ctx, json_mode=json_mode)

    parent_scope = resolve_cli_scope(project, None, allow_deliverable=False, out=out)
    project = parent_scope.project

    slug = slugify(name)
    if not slug:
        out.fail("invalid deliverable name", code=ErrorCode.INVALID_NAME, exit_code=2)

    deliv_scope = workspace.Scope(project=project, deliverable=slug)
    if deliv_scope.unit_dir.exists():
        out.fail(f"deliverable already exists: {deliv_scope.unit_dir}", code=ErrorCode.EXISTS)

    description = require_or_fail(description, arg_name="--description", label="Description")

    # Mutual exclusivity.
    if repo and shared:
        out.fail(
            "--repo and --shared are mutually exclusive",
            code=ErrorCode.CONFLICTING_FLAGS,
            exit_code=2,
        )

    # Validate --repo.
    repo_paths: list[Path] = []
    if repo:
        rp = Path(repo).expanduser().resolve()
        if not git_ops.is_git_repo(rp):
            out.fail(f"not a git repo: {rp}", code=ErrorCode.NOT_A_REPO)
        repo_paths.append(rp)

    # Inherit lifecycle from parent.
    parent_manifest = load_project_manifest(parent_scope.manifest_path)
    parent_lifecycle = parent_manifest.project.lifecycle
    try:
        lc = load_lifecycle(parent_lifecycle)
    except LifecycleNotFoundError:
        out.fail(
            f"parent project's lifecycle '{parent_lifecycle}' is unknown",
            code=ErrorCode.NOT_FOUND,
        )

    # Build repo specs (deliverable's own worktree is always 'code' if --repo given).
    repo_specs: list[RepoSpec] = []
    if repo_paths:
        try:
            user_slug = git_ops.git_user_slug(repo_paths[0])
        except Exception:
            user_slug = "user"
        repo_specs.append(
            RepoSpec(
                remote=str(repo_paths[0]),
                local_hint=str(repo_paths[0]),
                worktree="code",
                branch_prefix=f"{user_slug}/{project}-{slug}",
            )
        )

    if dry_run:
        log = OpLog()
        log.create_file(deliv_scope.manifest_path, size=0)
        log.create_file(deliv_scope.readme_path, size=0)
        log.create_file(deliv_scope.scope_md_path, size=0)
        log.create_file(deliv_scope.design_md_path, size=0)
        log.create_file(deliv_scope.phase_path, size=0)
        log.create_file(deliv_scope.lifecycle_lock_path, size=0)
        if repo_paths:
            log.create_worktree(
                deliv_scope.unit_dir / "code",
                source=repo_paths[0],
                branch=repo_specs[0].branch_prefix,
            )
        out.info(log.format_summary())
        return

    created_worktree: str | None = None
    modified_files: list[str] = []

    # Fire pre-deliverable-add, do the work, fire post-deliverable-add.
    try:
        with hook_event(
            "deliverable.create",
            project=project,
            deliverable=slug,
            payload={"description": description, "lifecycle": parent_lifecycle},
            positional_args=(slug,),
            out=out,
            no_verify=no_verify,
        ) as ev:
            # Reuse the same scaffold logic as `keel new`.
            from keel.commands._helpers import _scaffold_unit

            manifest = _scaffold_unit(
                scope=deliv_scope,
                name=slug,
                description=description,
                lifecycle=parent_lifecycle,
                repos=repo_specs,
                lc=lc,
            )

            # Persist `shared_worktree=True` if requested. `_scaffold_unit` always builds with
            # the default (False); we re-save the manifest here when --shared is set.
            if shared:
                manifest = ProjectManifest(
                    project=ProjectMeta(
                        name=manifest.project.name,
                        description=manifest.project.description,
                        created=manifest.project.created,
                        lifecycle=manifest.project.lifecycle,
                        shared_worktree=True,
                    ),
                    repos=[],
                    extensions=manifest.extensions,
                )
                save_project_manifest(deliv_scope.manifest_path, manifest)

            # Create worktree if --repo was provided.
            if repo_paths:
                wt_dest = deliv_scope.unit_dir / "code"
                try:
                    git_ops.create_worktree(
                        repo_paths[0], wt_dest, branch=repo_specs[0].branch_prefix
                    )
                    created_worktree = str(wt_dest)
                except git_ops.GitError as e:
                    out.info(f"Files are at {deliv_scope.unit_dir}; clean up manually if needed.")
                    out.fail(f"worktree creation failed: {e}", code=ErrorCode.GIT_FAILED)

            # AST-edit parent's design.md to reference the new deliverable.
            parent_design_path = parent_scope.design_md_path
            if parent_design_path.is_file():
                line = (
                    f"- **{slug}**: {description}. See [design](deliverables/{slug}/design.md).\n"
                )
                new_text = insert_under_heading(
                    parent_design_path.read_text(), "Deliverables", line
                )
                parent_design_path.write_text(new_text)
                modified_files.append(str(parent_design_path))

            ev.add_post_payload(
                {
                    "path": str(deliv_scope.unit_dir),
                    "modified_files": modified_files,
                    "worktree": created_worktree,
                }
            )
    except HookAborted as e:
        out.fail(
            f"deliverable.create aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {
            "deliverable_path": str(deliv_scope.unit_dir),
            "modified_files": modified_files,
            "worktree": created_worktree,
        },
        human_text=f"Deliverable created: {deliv_scope.unit_dir}",
    )
