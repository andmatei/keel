"""Tests for keel.ai.generate — AGENTS.md content generation."""

from __future__ import annotations

from keel.ai.generate import generate_agents_md
from keel.api import (
    Milestone,
    MilestonesManifest,
    Task,
    load_project_manifest,
    save_milestones_manifest,
    save_project_manifest,
)
from keel.workspace import Scope


def test_minimal_project(projects, make_project) -> None:
    """A project with no AI config gets default lifecycle triggers."""
    make_project("foo", description="the foo project")
    scope = Scope(project="foo")
    content = generate_agents_md(scope)
    assert "# Project: foo" in content
    assert "Phase: scoping" in content
    assert "scope.md" in content
    assert "design.md" in content
    assert "AI Workflow" in content
    assert "design-sync" in content


def test_includes_decisions(projects, make_project) -> None:
    proj = make_project("foo")
    (proj / "decisions" / "2026-01-01-choice.md").write_text("# Choice\n")
    (proj / "decisions" / "2026-01-02-other.md").write_text("# Other\n")
    content = generate_agents_md(Scope(project="foo"))
    assert "decisions/" in content
    assert "2 files" in content


def test_includes_milestones(projects, make_project) -> None:
    proj = make_project("foo")
    save_milestones_manifest(
        proj / "milestones.toml",
        MilestonesManifest(
            milestones=[
                Milestone(id="m1", title="Foundation", status="active"),
                Milestone(id="m2", title="Polish", status="planned"),
            ],
            tasks=[
                Task(id="t1", milestone="m1", title="Setup", status="done"),
                Task(id="t2", milestone="m1", title="Build", status="active"),
                Task(id="t3", milestone="m2", title="Docs", status="planned"),
            ],
        ),
    )
    content = generate_agents_md(Scope(project="foo"))
    assert "m1" in content
    assert "Foundation" in content
    assert "active" in content.lower()


def test_includes_active_work(projects, make_project) -> None:
    proj = make_project("foo")
    save_milestones_manifest(
        proj / "milestones.toml",
        MilestonesManifest(
            milestones=[Milestone(id="m1", title="Core", status="active")],
            tasks=[
                Task(id="t1", milestone="m1", title="API", status="active"),
                Task(id="t2", milestone="m1", title="Tests", status="planned"),
            ],
        ),
    )
    content = generate_agents_md(Scope(project="foo"))
    assert "Active Work" in content
    assert "API" in content


def test_includes_deliverables(projects, make_project, make_deliverable) -> None:
    make_deliverable(project_name="foo", name="alpha", description="Alpha deliverable")
    content = generate_agents_md(Scope(project="foo"))
    assert "alpha" in content


def test_ai_workflow_section(projects, make_project) -> None:
    """With triggers configured, produces an AI Workflow section."""
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {
        "triggers": {
            "task_done": {
                "event": "task.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "lightweight",
            },
            "milestone_done": {
                "event": "milestone.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "thorough",
            },
        }
    }
    save_project_manifest(proj / "project.toml", pm)
    content = generate_agents_md(Scope(project="foo"))
    assert "AI Workflow" in content
    assert "design-sync" in content
    assert "lightweight" in content
    assert "thorough" in content


def test_ai_disabled_no_workflow(projects, make_project) -> None:
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"enabled": False}
    save_project_manifest(proj / "project.toml", pm)
    content = generate_agents_md(Scope(project="foo"))
    assert "AI Workflow" not in content


def test_extra_content_appended(projects, make_project) -> None:
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"agents_md": {"extra": ".keel/agents-md-extra.md"}}
    save_project_manifest(proj / "project.toml", pm)
    (proj / ".keel" / "agents-md-extra.md").write_text("## Custom Instructions\nDo the thing.\n")
    content = generate_agents_md(Scope(project="foo"))
    assert "Custom Instructions" in content
    assert "Do the thing." in content


def test_extra_file_missing_no_error(projects, make_project) -> None:
    """Missing extra file should not crash — just skip."""
    proj = make_project("foo")
    pm = load_project_manifest(proj / "project.toml")
    pm.extensions["ai"] = {"agents_md": {"extra": ".keel/nonexistent.md"}}
    save_project_manifest(proj / "project.toml", pm)
    content = generate_agents_md(Scope(project="foo"))
    assert "# Project: foo" in content


def test_missing_design_docs(projects) -> None:
    """Project without scope.md or design.md still generates content."""
    proj = projects / "bare"
    proj.mkdir()
    from datetime import date
    from keel.manifest import ProjectManifest, ProjectMeta, save_project_manifest
    save_project_manifest(
        proj / "project.toml",
        ProjectManifest(
            project=ProjectMeta(name="bare", description="bare project", created=date(2026, 5, 15))
        ),
    )
    (proj / ".keel").mkdir()
    (proj / ".keel" / "phase").write_text("scoping\n")
    content = generate_agents_md(Scope(project="bare"))
    assert "# Project: bare" in content
