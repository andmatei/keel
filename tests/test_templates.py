"""Tests for the template renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from keel.templates import render, render_for_scope
from keel.workspace import Scope


# ---------------------------------------------------------------------------
# Existing smoke tests
# ---------------------------------------------------------------------------


def test_render_scope_md() -> None:
    out = render("scope_md.j2", name="foo", description="A test project")
    assert "# foo" in out
    assert "Scope Document" in out


def test_render_design_md() -> None:
    out = render("design_md.j2", name="foo", description="A test project")
    assert "# foo" in out


def test_render_decision_entry() -> None:
    out = render(
        "decision_entry.j2",
        date="2026-04-27",
        title="Pick a thing",
    )
    assert "# Pick a thing" in out
    assert "status: proposed" in out
    assert "2026-04-27" in out


# ---------------------------------------------------------------------------
# render() with search_dirs
# ---------------------------------------------------------------------------


def test_render_no_search_dirs_uses_package_default() -> None:
    """render() with no search_dirs falls through to package-bundled template."""
    out = render("scope_md.j2", name="bar", description="")
    assert "# bar" in out


def test_render_search_dirs_override_takes_precedence(tmp_path: Path) -> None:
    """render() picks up an override file from search_dirs before the package default."""
    override_dir = tmp_path / "overrides"
    override_dir.mkdir()
    (override_dir / "scope_md.j2").write_text("CUSTOM {{ name }}")

    out = render("scope_md.j2", search_dirs=[override_dir], name="myproject")
    assert out == "CUSTOM myproject"


def test_render_search_dirs_fallback_when_override_missing(tmp_path: Path) -> None:
    """render() falls back to package default when override dir exists but lacks the template."""
    override_dir = tmp_path / "overrides"
    override_dir.mkdir()
    # Do NOT write scope_md.j2 in override_dir

    out = render("scope_md.j2", search_dirs=[override_dir], name="baz", description="")
    # Should still return the real package template
    assert "# baz" in out
    assert "Scope Document" in out


def test_render_nonexistent_search_dir_ignored(tmp_path: Path) -> None:
    """render() silently ignores search_dirs entries that don't exist on disk."""
    nonexistent = tmp_path / "does_not_exist"
    out = render("scope_md.j2", search_dirs=[nonexistent], name="qux", description="")
    assert "# qux" in out


# ---------------------------------------------------------------------------
# render_for_scope()
# ---------------------------------------------------------------------------


def test_render_for_scope_project_override(tmp_path: Path, monkeypatch) -> None:
    """render_for_scope() picks up a project-level override at <unit_dir>/.keel/templates/<template>."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "myproj"
    proj.mkdir()

    template_dir = proj / ".keel" / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "scope_md.j2").write_text("PROJECT OVERRIDE {{ name }}")

    scope = Scope(project="myproj")
    out = render_for_scope("scope_md.j2", scope=scope, name="myproj", description="")
    assert out == "PROJECT OVERRIDE myproj"


def test_render_for_scope_workspace_override(tmp_path: Path, monkeypatch) -> None:
    """render_for_scope() picks up a workspace-level override when no project override exists."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "myproj"
    proj.mkdir()
    # No project-level .keel/templates/

    workspace_template_dir = tmp_path / ".keel" / "templates"
    workspace_template_dir.mkdir(parents=True)
    (workspace_template_dir / "scope_md.j2").write_text("WORKSPACE OVERRIDE {{ name }}")

    scope = Scope(project="myproj")
    out = render_for_scope("scope_md.j2", scope=scope, name="myproj", description="")
    assert out == "WORKSPACE OVERRIDE myproj"


def test_render_for_scope_project_override_beats_workspace(tmp_path: Path, monkeypatch) -> None:
    """render_for_scope() project-level override takes priority over workspace-level."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "myproj"
    proj.mkdir()

    project_tpl_dir = proj / ".keel" / "templates"
    project_tpl_dir.mkdir(parents=True)
    (project_tpl_dir / "scope_md.j2").write_text("PROJECT {{ name }}")

    workspace_tpl_dir = tmp_path / ".keel" / "templates"
    workspace_tpl_dir.mkdir(parents=True)
    (workspace_tpl_dir / "scope_md.j2").write_text("WORKSPACE {{ name }}")

    scope = Scope(project="myproj")
    out = render_for_scope("scope_md.j2", scope=scope, name="myproj", description="")
    assert out == "PROJECT myproj"


def test_render_for_scope_falls_back_to_package_default(tmp_path: Path, monkeypatch) -> None:
    """render_for_scope() falls back to package default when no overrides exist."""
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    proj = tmp_path / "myproj"
    proj.mkdir()
    # No .keel/templates/ anywhere

    scope = Scope(project="myproj")
    out = render_for_scope("scope_md.j2", scope=scope, name="myproj", description="")
    assert "# myproj" in out
    assert "Scope Document" in out
