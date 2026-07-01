"""Manifest schemas, TOML I/O, and query helpers.

Split into three submodules:
- `models`: Pydantic schemas (RepoSpec, ProjectManifest, Milestone, Task, MilestonesManifest)
- `io`: load/save functions
- `queries`: find_milestone, find_task, edit_* context managers

Re-exported here for backward compatibility — callers can `from keel.manifest import X`.
"""

from keel.manifest.io import (
    load_milestones_manifest,
    load_project_manifest,
    save_milestones_manifest,
    save_project_manifest,
)
from keel.manifest.models import (
    Milestone,
    MilestonesManifest,
    ProjectManifest,
    ProjectMeta,
    RepoSpec,
    Task,
)
from keel.manifest.queries import (
    edit_milestones,
    edit_project_manifest,
    find_milestone,
    find_task,
    get_milestone,
    get_task,
)

__all__ = [
    "Milestone",
    "MilestonesManifest",
    "ProjectManifest",
    "ProjectMeta",
    "RepoSpec",
    "Task",
    "load_milestones_manifest",
    "load_project_manifest",
    "save_milestones_manifest",
    "save_project_manifest",
    "edit_milestones",
    "edit_project_manifest",
    "find_milestone",
    "find_task",
    "get_milestone",
    "get_task",
]
