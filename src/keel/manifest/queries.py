"""Manifest query helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from keel.manifest.io import (
    load_milestones_manifest,
    load_project_manifest,
    save_milestones_manifest,
    save_project_manifest,
)
from keel.manifest.models import Milestone, MilestonesManifest, ProjectManifest, Task

if TYPE_CHECKING:
    from keel.output import Output
    from keel.workspace import Scope


def find_milestone(manifest: MilestonesManifest, id: str) -> Milestone | None:
    """Return the milestone with the given id, or None."""
    return next((m for m in manifest.milestones if m.id == id), None)


def find_task(manifest: MilestonesManifest, id: str) -> Task | None:
    """Return the task with the given id, or None."""
    return next((t for t in manifest.tasks if t.id == id), None)


def get_milestone(manifest: MilestonesManifest, id: str, *, out: "Output") -> Milestone:
    """Return the milestone with the given id, or call out.fail() with NOT_FOUND."""
    m = find_milestone(manifest, id)
    if m is None:
        from keel.errors import ErrorCode

        out.fail(f"no milestone with id '{id}'", code=ErrorCode.NOT_FOUND)
    return m


def get_task(manifest: MilestonesManifest, id: str, *, out: "Output") -> Task:
    """Return the task with the given id, or call out.fail() with NOT_FOUND."""
    t = find_task(manifest, id)
    if t is None:
        from keel.errors import ErrorCode

        out.fail(f"no task with id '{id}'", code=ErrorCode.NOT_FOUND)
    return t


@contextmanager
def edit_project_manifest(path: Path) -> Iterator[ProjectManifest]:
    """Load -> yield -> save a project manifest without dropping unknown fields."""
    manifest = load_project_manifest(path)
    yield manifest
    manifest = ProjectManifest.model_validate(manifest.model_dump())
    path.parent.mkdir(parents=True, exist_ok=True)
    save_project_manifest(path, manifest)


@contextmanager
def edit_milestones(scope: "Scope") -> Iterator[MilestonesManifest]:
    """Load → yield → save the milestones manifest at the scope's path.

    Validates the manifest graph on load. If the file has integrity issues
    (cycles, dangling refs, duplicate IDs), raises ``GraphError`` before
    yielding so callers never see corrupt state.

    Usage:
        with edit_milestones(scope) as manifest:
            # mutate manifest in place
    """
    path = scope.milestones_manifest_path
    manifest = load_milestones_manifest(path, validate=True)
    yield manifest
    path.parent.mkdir(parents=True, exist_ok=True)
    save_milestones_manifest(path, manifest)
