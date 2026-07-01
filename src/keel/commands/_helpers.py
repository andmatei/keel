"""Shared helpers for project/deliverable scaffold commands."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from keel import workspace
from keel.templates import render_for_scope
from keel.api import (
    ProjectManifest,
    ProjectMeta,
    RepoSpec,
    save_project_manifest,
)
from keel.git_ops import git_user_slug
from keel.lifecycles import Lifecycle, lifecycle_source_path


def _build_repo_specs(slug: str, repo_paths: list[Path]) -> list[RepoSpec]:
    """Construct RepoSpec entries for each validated source repo path.

    Worktree path defaults to "code" when single, "code-<repo>" otherwise.
    """
    specs: list[RepoSpec] = []
    for rp in repo_paths:
        worktree_name = "code" if len(repo_paths) == 1 else f"code-{rp.name}"
        try:
            user_slug = git_user_slug(rp)
        except Exception:
            user_slug = "user"
        branch_prefix_suffix = "-base" if len(repo_paths) == 1 else f"-{rp.name}-base"
        specs.append(
            RepoSpec(
                remote=str(rp),
                local_hint=str(rp),
                worktree=worktree_name,
                branch_prefix=f"{user_slug}/{slug}{branch_prefix_suffix}",
            )
        )
    return specs


def _scaffold_unit(
    *,
    scope: workspace.Scope,
    name: str,
    description: str,
    lifecycle: str,
    repos: list[RepoSpec],
    lc: Lifecycle,
    tags: list[str] | None = None,
) -> ProjectManifest:
    """Write all the new layout files for a unit (project or deliverable).

    Caller is responsible for the unit-doesn't-exist precheck; this function
    is non-idempotent on existing units.

    Returns the persisted manifest so callers can use it for follow-up steps
    (e.g. worktree creation in `keel new`).
    """
    # Unit root + manifest.
    scope.unit_dir.mkdir(parents=True, exist_ok=True)
    manifest = ProjectManifest(
        project=ProjectMeta(
            name=name,
            description=description,
            created=date.today(),
            lifecycle=lifecycle,
            tags=tags or [],
        ),
        repos=repos,
    )
    save_project_manifest(scope.manifest_path, manifest)

    # Tool state under .keel/.
    scope.keel_dir.mkdir(exist_ok=True)
    scope.phase_path.write_text(f"{lc.initial}\n")

    # Lifecycle snapshot — verbatim copy of the resolved TOML.
    src_path = lifecycle_source_path(lifecycle)
    shutil.copyfile(src_path, scope.lifecycle_lock_path)

    # Human-authored content at the unit root.
    scope.scope_md_path.write_text(
        render_for_scope("scope_md.j2", scope=scope, name=name, description=description)
    )
    scope.design_md_path.write_text(
        render_for_scope("design_md.j2", scope=scope, name=name, description=description)
    )
    scope.decisions_dir.mkdir(exist_ok=True)

    # README.
    scope.readme_path.write_text(
        render_for_scope(
            "readme_md.j2",
            scope=scope,
            project=manifest.project,
            lifecycle=lc,
            phase=lc.initial,
            has_milestones=False,
            repos=manifest.repos,
        )
    )

    return manifest
