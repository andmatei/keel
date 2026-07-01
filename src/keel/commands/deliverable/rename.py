"""`keel deliverable rename <old> <new>`."""

from __future__ import annotations

import shutil

import typer

from keel import git, workspace
from keel.api import (
    HINT_LIST_DELIVERABLES,
    ErrorCode,
    OpLog,
    Output,
    load_project_manifest,
    resolve_cli_scope,
    save_project_manifest,
)
from keel.hooks import HookAborted, hook_event, hookable
from keel.markdown_edit import insert_under_heading, remove_bullet_under_heading


@hookable("deliverable.rename")
def cmd_rename(
    ctx: typer.Context,
    old: str = typer.Argument(...),
    new: str = typer.Argument(...),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name. Auto-detected from CWD if omitted."
    ),
    rename_branch: bool = typer.Option(
        True,
        "--rename-branch/--no-rename-branch",
        help="Also rename the worktree's git branch (default true).",
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip interactive prompts (description, etc.)."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip deliverable.rename.pre hooks."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print intended operations and exit; write nothing."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Rename a deliverable."""
    out = Output.from_context(ctx, json_mode=json_mode)

    scope = resolve_cli_scope(project, None, allow_deliverable=False, out=out)
    project = scope.project
    if not workspace.deliverable_exists(project, old):
        out.fail(
            f"deliverable not found: {project}/{old}\n  {HINT_LIST_DELIVERABLES}",
            code=ErrorCode.NOT_FOUND,
        )
    if workspace.deliverable_exists(project, new):
        out.fail(f"target already exists: {project}/{new}", code=ErrorCode.EXISTS)

    old_scope = workspace.Scope(project=project, deliverable=old)
    new_scope = workspace.Scope(project=project, deliverable=new)
    old_path = old_scope.unit_dir
    new_path = new_scope.unit_dir

    if dry_run:
        log = OpLog()
        log.modify_file(old_path, diff=f"rename → {new_path}")
        out.info(log.format_summary())
        return

    try:
        with hook_event(
            "deliverable.rename",
            project=project,
            deliverable=old,
            payload={"old_name": old, "new_name": new, "project": project},
            positional_args=(old, new),
            out=out,
            no_verify=no_verify,
        ):
            # 1a. If a worktree exists, move it properly via git first
            old_code = old_path / "code"
            if old_code.is_dir():
                new_path.mkdir(parents=True, exist_ok=True)
                git.move_worktree(old_code, new_path / "code")

            # 1b. Move the design dir (and any other contents)
            new_path.mkdir(parents=True, exist_ok=True)
            for child in list(old_path.iterdir()):
                shutil.move(str(child), str(new_path / child.name))

            # 1c. rmdir the now-empty old path
            if old_path.exists() and not any(old_path.iterdir()):
                old_path.rmdir()

            # 2. Update manifest's `name`
            manifest_path = new_scope.manifest_path
            m = load_project_manifest(manifest_path)
            new_repos = list(m.repos)

            # 3. (Optional) branch rename
            code_dir = new_path / "code"
            if code_dir.is_dir() and rename_branch and new_repos:
                old_branch = new_repos[0].branch_prefix
                if old_branch and old_branch.endswith(f"-{old}"):
                    new_branch = old_branch[: -len(f"-{old}")] + f"-{new}"
                    try:
                        git.rename_branch(code_dir, old=old_branch, new=new_branch)
                        new_repos[0] = new_repos[0].model_copy(update={"branch_prefix": new_branch})
                    except git.GitError as e:
                        out.warn(f"branch rename failed: {e}")

            new_manifest = m.model_copy(
                update={
                    "project": m.project.model_copy(update={"name": new}),
                    "repos": new_repos,
                }
            )
            save_project_manifest(manifest_path, new_manifest)

            # 4. Update parent design.md references (the source of truth post-0.0.3).
            description = m.project.description
            parent_scope = workspace.Scope(project=project, deliverable=None)
            parent_design = parent_scope.design_md_path
            if parent_design.is_file():
                text = remove_bullet_under_heading(
                    parent_design.read_text(), "Deliverables", f"- **{old}**:"
                )
                text = insert_under_heading(
                    text,
                    "Deliverables",
                    f"- **{new}**: {description}. See [design](deliverables/{new}/design.md).\n",
                )
                parent_design.write_text(text)
    except HookAborted as e:
        out.fail(
            f"deliverable.rename aborted: {e} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    out.result(
        {"old": str(old_path), "new": str(new_path)},
        human_text=f"Deliverable renamed: {old} → {new}",
    )
