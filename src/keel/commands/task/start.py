"""`keel task start <id>`."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from keel import git_ops
from keel.api import (
    ErrorCode,
    MissingDepBranch,
    Output,
    ProjectManifest,
    edit_milestones,
    get_task,
    load_milestones_manifest,
    load_project_manifest,
    resolve_base,
    resolve_cli_scope,
    safe_push,
    slugify,
    with_provider,
)
from keel.hooks import HookAborted, hook_event, hookable


def _default_branch(user: str, project: str, milestone_id: str, task_id: str) -> str:
    return f"{slugify(user)}/{project}-{milestone_id}-{task_id}"


@hookable("task.status")
def cmd_start(
    ctx: typer.Context,
    id: str = typer.Argument(...),
    deliverable: str | None = typer.Option(
        None,
        "-D",
        "--deliverable",
        help="Scope: a deliverable instead of the project. Auto-detected from CWD.",
    ),
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project name. Auto-detected from CWD if omitted.",
    ),
    branch: str | None = typer.Option(
        None, "--branch", help="Override the auto-computed branch name."
    ),
    base: str | None = typer.Option(
        None,
        "--base",
        help="Git ref to branch from. Overrides the depends_on heuristic.",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        "-r",
        help="Worktree-dir name (from project manifest's [[repos]]). Required when project has multiple repos.",
    ),
    no_worktree: bool = typer.Option(
        False,
        "--no-worktree",
        help="Record the branch name and mark task active, but skip git worktree creation.",
    ),
    reopen: bool = typer.Option(
        False, "--reopen", help="Allow re-starting a task that is done or cancelled."
    ),
    no_push: bool = typer.Option(
        False, "--no-push", help="Skip pushing to the configured ticketing provider."
    ),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip task.status.pre hooks."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON to stdout."),
) -> None:
    """Start work on a task (planned -> active). Records the branch name and creates a worktree."""
    out = Output.from_context(ctx, json_mode=json_mode)

    # Warn if --repo or --base are passed alongside --no-worktree; they'll be ignored.
    if no_worktree and (repo is not None or base is not None):
        out.warn("--repo and --base are ignored when --no-worktree is set")

    scope = resolve_cli_scope(project, deliverable, out=out)

    # Pre-load to capture current status before mutation.
    pre = load_milestones_manifest(scope.milestones_manifest_path, validate=True)
    pre_task = get_task(pre, id, out=out)
    from_status = pre_task.status

    # These are populated inside the hook_event block so they can be added to
    # the post payload before the context manager exits.
    worktree_dest: Path | None = None
    branch_base: str | None = None

    try:
        with hook_event(
            "task.status",
            project=scope.project,
            deliverable=scope.deliverable,
            payload={"id": id, "from": from_status, "to": "active", "command": "start", "forced": reopen},
            positional_args=(id,),
            out=out,
            no_verify=no_verify,
        ) as e:
            with edit_milestones(scope) as manifest:
                task = get_task(manifest, id, out=out)

                allowed = task.status == "planned" or (
                    task.status in ("done", "cancelled") and reopen
                )
                if allowed:
                    user = os.environ.get("USER", "user")
                    task.branch = branch or _default_branch(user, scope.project, task.milestone, task.id)
                    task.status = "active"
                elif task.status in ("done", "cancelled"):
                    out.fail(
                        f"cannot start task in status '{task.status}' "
                        f"(use --reopen to re-start a done or cancelled task)",
                        code=ErrorCode.INVALID_STATE,
                    )
                else:
                    out.fail(
                        f"cannot start task in status '{task.status}'",
                        code=ErrorCode.INVALID_STATE,
                    )

            # At this point milestones.toml has been updated (status=active, branch recorded).
            # Now attempt worktree creation unless explicitly skipped.

            if not no_worktree:
                proj_m: ProjectManifest = load_project_manifest(scope.manifest_path)
                repos = proj_m.repos

                if not repos:
                    out.warn(
                        "no [[repos]] declared; skipping worktree creation "
                        "(run 'keel code add' to configure)"
                    )
                else:
                    # Resolve which repo to use
                    if repo is not None:
                        target = next((r for r in repos if r.worktree == repo), None)
                        if target is None:
                            out.fail(
                                f"no repo with worktree dir '{repo}' found in manifest",
                                code=ErrorCode.NOT_FOUND,
                            )
                    elif len(repos) > 1:
                        names = ", ".join(r.worktree for r in repos)
                        out.fail(
                            f"project has multiple repos ({names}); use --repo NAME to choose one",
                            code=ErrorCode.CONFLICTING_FLAGS,
                            exit_code=2,
                        )
                    else:
                        target = repos[0]

                    # Resolve base branch
                    try:
                        base_ref = resolve_base(
                            scope.milestones_manifest_path,
                            task.depends_on,
                            base,
                        )
                    except MissingDepBranch as exc:
                        if exc.reason == "not found":
                            out.fail(
                                f"task '{exc.dep_id}' not found in manifest",
                                code=ErrorCode.NOT_FOUND,
                            )
                        else:
                            out.fail(
                                f"task '{exc.dep_id}' has no branch; start that task first",
                                code=ErrorCode.INVALID_STATE,
                            )

                    branch_base = base_ref  # may be None — create_worktree handles that

                    dest = scope.unit_dir / f"{target.worktree}-{task.id}"
                    repo_path = Path(target.remote)

                    try:
                        git_ops.create_worktree(repo_path, dest, branch=task.branch, base=branch_base)
                        worktree_dest = dest
                    except git_ops.GitError as err:
                        err_msg = str(err)
                        if "already exists" in err_msg.lower() or "already checked out" in err_msg.lower():
                            hint = "branch already exists — use --branch to pick a different name or delete the existing branch"
                            out.fail(
                                f"worktree creation failed: {err}\n  hint: {hint}",
                                code=ErrorCode.GIT_FAILED,
                            )
                        out.fail(f"worktree creation failed: {err}", code=ErrorCode.GIT_FAILED)

            e.add_post_payload({
                "worktree": str(worktree_dest) if worktree_dest else None,
                "branch_base": branch_base,
            })

    except HookAborted as exc:
        out.fail(
            f"task.status aborted: {exc} (use --no-verify to override)",
            code=ErrorCode.PREFLIGHT_BLOCKED,
        )

    provider = with_provider(scope, no_push=no_push)
    if provider is not None and provider.name in task.tickets:
        tid = task.tickets[provider.name]
        safe_push(out, "transition", lambda: provider.transition(tid, "active"))

    result_data = task.model_dump()
    result_data["worktree"] = str(worktree_dest) if worktree_dest is not None else None
    result_data["branch_base"] = branch_base

    out.result(
        result_data,
        human_text=f"Task started: {id} (branch: {task.branch})",
    )
