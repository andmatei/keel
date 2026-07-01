"""Public API for keel and keel plugins.

Anything exported from this module is considered stable across minor releases.
Plugin authors should import only from `keel.api` (or `keel.testing` for fixtures).

Anything outside `keel.api` and `keel.testing` is internal and may change.
"""

from __future__ import annotations

from pathlib import Path

from keel.dryrun import Op, OpLog
from keel.errors import (
    HINT_LIST_DECISIONS,
    HINT_LIST_DELIVERABLES,
    HINT_LIST_PROJECTS,
    HINT_PASS_PROJECT,
    ErrorCode,
)

from keel.hooks import (
    HookAborted,
    HookEvent,
    hook_event,
    hookable,
    subscribes_to,
)

from keel.ai.config import AIConfig, parse_ai_config, resolve_triggers

from keel.lifecycle import (
    DEFAULT_MILESTONE_STATE,
    DEFAULT_PHASE,
    DEFAULT_TASK_STATE,
    MILESTONE_STATES,
    PHASES,
    TASK_STATES,
    is_terminal_milestone_state,
    is_terminal_task_state,
    is_valid_milestone_state,
    is_valid_phase,
    is_valid_task_state,
    next_phase,
)
from keel.lifecycles import (
    Lifecycle,
    LifecycleNotFoundError,
    LifecycleState,
    iter_lifecycles,
    load_lifecycle,
)

from keel.manifest import (
    Milestone,
    MilestonesManifest,
    ProjectManifest,
    ProjectMeta,
    RepoSpec,
    Task,
    edit_milestones,
    find_milestone,
    find_task,
    get_milestone,
    get_task,
    load_milestones_manifest,
    load_project_manifest,
    save_milestones_manifest,
    save_project_manifest,
)

from keel.milestones import (
    GraphError,
    blocked_tasks,
    ready_tasks,
    topological_sort,
    validate_dag,
)

from keel.output import Output
from keel.prompts import confirm_destructive, is_interactive, require_or_fail
from keel.util import slugify

from keel.ticketing import get_provider_for_project, safe_push, with_provider
from keel.ticketing.base import Ticket, TicketProvider
from keel.ticketing.registry import list_providers, load_provider

from keel.workspace import (
    Scope,
    deliverable_dir,
    deliverable_exists,
    detect_scope,
    iter_projects,
    project_dir,
    project_exists,
    projects_dir,
    read_phase,
    resolve_cli_scope,
)


class MissingDepBranch(ValueError):
    """Raised when a dependency task cannot supply a base branch.

    ``reason`` is one of:
    - ``"not found"``  — the dep task ID doesn't exist in the manifest
    - ``"no branch"``  — the dep task exists but has no branch recorded yet
    """

    def __init__(self, dep_id: str, reason: str) -> None:
        self.dep_id = dep_id
        self.reason = reason
        super().__init__(f"dependency '{dep_id}': {reason}")


def resolve_base(
    milestones_path: Path,
    task_depends_on: list[str],
    explicit_base: str | None,
) -> str | None:
    """Resolve the base branch for worktree creation.

    Resolution order:
    1. ``explicit_base`` if provided
    2. Branch of the last dependency (if task has ``depends_on``)
    3. ``None`` (caller will use ``git_ops.default_branch`` via ``create_worktree``)

    Raises ``MissingDepBranch`` if the last dependency has no branch recorded
    or doesn't exist in the manifest.
    """
    if explicit_base is not None:
        return explicit_base

    if not task_depends_on:
        return None

    ms_manifest = load_milestones_manifest(milestones_path)
    all_tasks = {t.id: t for t in ms_manifest.tasks}

    last_dep_id = task_depends_on[-1]
    dep_task = all_tasks.get(last_dep_id)
    if dep_task is None:
        raise MissingDepBranch(last_dep_id, "not found")
    if not dep_task.branch:
        raise MissingDepBranch(last_dep_id, "no branch recorded")

    return dep_task.branch


__all__ = [
    # Task branch resolution
    "MissingDepBranch",
    "resolve_base",
    # Errors
    "ErrorCode",
    "HINT_LIST_DECISIONS",
    "HINT_LIST_DELIVERABLES",
    "HINT_LIST_PROJECTS",
    "HINT_PASS_PROJECT",
    # Lifecycle
    "DEFAULT_MILESTONE_STATE",
    "DEFAULT_PHASE",
    "DEFAULT_TASK_STATE",
    "MILESTONE_STATES",
    "PHASES",
    "TASK_STATES",
    "is_terminal_milestone_state",
    "is_terminal_task_state",
    "is_valid_milestone_state",
    "is_valid_phase",
    "is_valid_task_state",
    "next_phase",
    # Lifecycles (FSM)
    "Lifecycle",
    "LifecycleNotFoundError",
    "LifecycleState",
    "iter_lifecycles",
    "load_lifecycle",
    # Manifest
    "Milestone",
    "MilestonesManifest",
    "ProjectManifest",
    "ProjectMeta",
    "RepoSpec",
    "Task",
    "edit_milestones",
    "find_milestone",
    "find_task",
    "get_milestone",
    "get_task",
    "load_milestones_manifest",
    "load_project_manifest",
    "save_milestones_manifest",
    "save_project_manifest",
    # Milestones graph helpers
    "GraphError",
    "blocked_tasks",
    "ready_tasks",
    "topological_sort",
    "validate_dag",
    # Dryrun
    "Op",
    "OpLog",
    # Output
    "Output",
    # Hooks
    "HookAborted",
    "HookEvent",
    "hook_event",
    "hookable",
    "subscribes_to",
    # AI config
    "AIConfig",
    "parse_ai_config",
    "resolve_triggers",
    # Prompts
    "confirm_destructive",
    "is_interactive",
    "require_or_fail",
    # Util
    "slugify",
    # Workspace
    "Scope",
    "deliverable_dir",
    "deliverable_exists",
    "detect_scope",
    "iter_projects",
    "project_dir",
    "project_exists",
    "projects_dir",
    "read_phase",
    "resolve_cli_scope",
    # Ticketing
    "Ticket",
    "TicketProvider",
    "get_provider_for_project",
    "with_provider",
    "safe_push",
    "list_providers",
    "load_provider",
]
