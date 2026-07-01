"""Pytest fixtures for keel and keel plugin authors.

Add this to your conftest.py or pytest config:

    pytest_plugins = ["keel.testing"]

Provides:
- `projects` — isolated PROJECTS_DIR at tmp_path
- `make_project` — factory creating a project with manifest + scaffold files
- `make_deliverable` — factory creating a deliverable inside a project
- `source_repo` — a real one-commit git repo at tmp_path/_source_repo
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from keel.manifest import (
    ProjectManifest,
    ProjectMeta,
    save_project_manifest,
)
from keel.ticketing.mock import MockProvider

__all__ = [
    "MockProvider",
    "projects",
    "make_project",
    "make_deliverable",
    "source_repo",
    "mock_ticket_provider",
]


@pytest.fixture
def projects(tmp_path, monkeypatch) -> Path:
    """Isolated `~/projects/` workspace at tmp_path."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def make_project(projects) -> Callable[..., Path]:
    """Factory: create a project with the new (v0.1.0) layout — manifest at root, .keel/ for state."""

    def _make(
        name: str = "foo",
        description: str = "test project",
        lifecycle: str = "default",
        tags: list[str] | None = None,
    ) -> Path:
        proj = projects / name
        proj.mkdir(parents=True, exist_ok=True)

        # Manifests at the unit root.
        (proj / "decisions").mkdir(exist_ok=True)
        save_project_manifest(
            proj / "project.toml",
            ProjectManifest(
                project=ProjectMeta(
                    name=name,
                    description=description,
                    created=date(2026, 5, 5),
                    lifecycle=lifecycle,
                    tags=tags or [],
                ),
                repos=[],
            ),
        )

        # Tool state under .keel/.
        (proj / ".keel").mkdir(exist_ok=True)
        (proj / ".keel" / "phase").write_text("scoping\n")

        # Minimal human-authored content so design-walking commands have something to read.
        (proj / "scope.md").write_text(f"# {name}\n\nScope.\n")
        (proj / "design.md").write_text(f"# {name} — design\n\n")

        return proj

    return _make


@pytest.fixture
def make_deliverable(make_project) -> Callable[..., Path]:
    """Factory: create a deliverable inside a (possibly new) project, using the new layout.

    Per Plan 8, deliverables collapse onto the same `ProjectManifest` schema as projects.
    The manifest lives at `<deliverable>/project.toml` (NOT `deliverable.toml`).
    """

    def _make(
        project_name: str = "foo",
        name: str = "bar",
        description: str = "test deliverable",
        shared_worktree: bool = False,
        lifecycle: str = "default",
        tags: list[str] | None = None,
    ) -> Path:
        from keel import workspace

        if not workspace.project_dir(project_name).is_dir():
            make_project(project_name)
        deliv = workspace.deliverable_dir(project_name, name)
        deliv.mkdir(parents=True, exist_ok=True)

        # Manifests at the deliverable's unit root.
        (deliv / "decisions").mkdir(exist_ok=True)
        save_project_manifest(
            deliv / "project.toml",
            ProjectManifest(
                project=ProjectMeta(
                    name=name,
                    description=description,
                    created=date(2026, 5, 5),
                    lifecycle=lifecycle,
                    shared_worktree=shared_worktree,
                    tags=tags or [],
                ),
                repos=[],
            ),
        )

        # Tool state under .keel/.
        (deliv / ".keel").mkdir(exist_ok=True)
        (deliv / ".keel" / "phase").write_text("scoping\n")

        # Minimal human-authored content.
        (deliv / "scope.md").write_text(f"# {name}\n\nScope.\n")
        (deliv / "design.md").write_text(f"# {name} — design\n\n")

        return deliv

    return _make


@pytest.fixture
def source_repo(tmp_path) -> Path:
    """A real git repo with one commit, suitable for worktree creation."""
    repo = tmp_path / "_source_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def mock_ticket_provider() -> MockProvider:
    """A fresh MockProvider instance for each test."""
    return MockProvider()
