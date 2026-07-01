"""Manifest TOML I/O helpers."""

import tomllib
from pathlib import Path

import tomlkit

from keel.io import atomic_write
from keel.manifest.models import (
    MilestonesManifest,
    ProjectManifest,
)


def _dict_compact(d: dict) -> dict:
    """Strip None values and empty containers from a model dict for clean TOML output."""
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def load_project_manifest(path: Path) -> ProjectManifest:
    """Read and validate a `project.toml`."""
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return ProjectManifest.model_validate(raw)


def save_project_manifest(path: Path, manifest: ProjectManifest) -> None:
    """Write a `project.toml`."""
    doc = tomlkit.document()
    project_dict = _dict_compact(manifest.project.model_dump())
    doc["project"] = project_dict
    if manifest.repos:
        repos_array = tomlkit.aot()
        for r in manifest.repos:
            repos_array.append(tomlkit.item(_dict_compact(r.model_dump())))
        doc["repos"] = repos_array
    if manifest.extensions:
        doc["extensions"] = tomlkit.item(manifest.extensions)
    atomic_write(path, tomlkit.dumps(doc))


def load_milestones_manifest(path: Path, *, validate: bool = False) -> MilestonesManifest:
    """Read `milestones.toml`. Returns an empty manifest if the file doesn't exist.

    When *validate* is True, runs the full DAG validation (duplicate IDs,
    referential integrity, cycle detection) after parsing.
    """
    if not path.is_file():
        return MilestonesManifest()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    manifest = MilestonesManifest.model_validate(raw)
    if validate and (manifest.milestones or manifest.tasks):
        from keel.milestones import validate_dag

        validate_dag(manifest)
    return manifest


def save_milestones_manifest(path: Path, manifest: MilestonesManifest) -> None:
    """Write a `milestones.toml`."""
    doc = tomlkit.document()
    if manifest.milestones:
        ms_array = tomlkit.aot()
        for m in manifest.milestones:
            ms_array.append(tomlkit.item(_dict_compact(m.model_dump())))
        doc["milestones"] = ms_array
    if manifest.tasks:
        ts_array = tomlkit.aot()
        for t in manifest.tasks:
            ts_array.append(tomlkit.item(_dict_compact(t.model_dump())))
        doc["tasks"] = ts_array
    atomic_write(path, tomlkit.dumps(doc))
