"""Tests for `keel list`."""

import json

from typer.testing import CliRunner

from keel.app import app

runner = CliRunner()


def test_list_empty(projects) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # Empty workspace prints either nothing or a header but no project lines.
    assert "(no projects)" in result.stdout or result.stdout.strip() == ""


def test_list_one_project(projects, make_project) -> None:
    make_project("foo", "first project")
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "foo" in result.stdout


def test_list_shows_phase(projects, make_project) -> None:
    make_project("foo", "first project")
    result = runner.invoke(app, ["list"])
    assert "scoping" in result.stdout


def test_list_json_empty_returns_empty_list(projects) -> None:
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"projects": []}


def test_list_json_shape(projects, make_project) -> None:
    make_project("foo", "first project")
    make_project("bar", "second project")
    result = runner.invoke(app, ["list", "--json"])
    payload = json.loads(result.stdout)
    assert "projects" in payload
    names = {p["name"] for p in payload["projects"]}
    assert names == {"foo", "bar"}
    for p in payload["projects"]:
        assert {"name", "phase", "description", "deliverable_count"} <= p.keys()


def test_list_phase_filter(projects, make_project) -> None:
    make_project("foo", "scoping project")
    bar = make_project("bar", "implementing project")
    (bar / ".keel" / "phase").write_text("implementing\n")

    result = runner.invoke(app, ["list", "--phase", "implementing"])
    assert result.exit_code == 0
    assert "bar" in result.stdout
    assert "foo" not in result.stdout


def test_list_phase_filter_no_match(projects, make_project) -> None:
    """When --phase filter matches nothing but projects exist, message reflects that."""
    make_project("foo", "scoping project")
    result = runner.invoke(app, ["list", "--phase", "done"])
    assert result.exit_code == 0
    assert "no projects in phase 'done'" in result.stdout


def test_list_with_active_columns(projects, make_project, monkeypatch) -> None:
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["milestone", "start", "m1"])
    result = runner.invoke(app, ["list", "--json"])
    data = json.loads(result.stdout)
    proj_entry = next(p for p in data["projects"] if p["name"] == "foo")
    assert proj_entry["active_milestones"] == 1
    assert proj_entry["active_tasks"] == 0


def test_list_active_filter(projects, make_project, monkeypatch) -> None:
    make_project("alpha")  # no milestones — not active
    proj_b = make_project("beta")
    monkeypatch.chdir(proj_b)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M1"])
    runner.invoke(app, ["milestone", "start", "m1"])
    monkeypatch.chdir(proj_b.parent)  # leave the project dir
    result = runner.invoke(app, ["list", "--active", "--json"])
    data = json.loads(result.stdout)
    names = {p["name"] for p in data["projects"]}
    assert names == {"beta"}


def test_list_tag_filter(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj_a = make_project("alpha", "a desc")
    proj_b = make_project("beta", "b desc")
    m_a = load_project_manifest(proj_a / "project.toml")
    m_a.project.tags = ["api", "research"]
    save_project_manifest(proj_a / "project.toml", m_a)
    m_b = load_project_manifest(proj_b / "project.toml")
    m_b.project.tags = ["api", "webhook"]
    save_project_manifest(proj_b / "project.toml", m_b)

    result = runner.invoke(app, ["list", "--tag", "api", "--json"])
    data = json.loads(result.stdout)
    names = {p["name"] for p in data["projects"]}
    assert names == {"alpha", "beta"}


def test_list_tag_filter_and_semantics(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj_a = make_project("alpha")
    proj_b = make_project("beta")
    m_a = load_project_manifest(proj_a / "project.toml")
    m_a.project.tags = ["api", "research"]
    save_project_manifest(proj_a / "project.toml", m_a)
    m_b = load_project_manifest(proj_b / "project.toml")
    m_b.project.tags = ["api", "webhook"]
    save_project_manifest(proj_b / "project.toml", m_b)

    result = runner.invoke(app, ["list", "--tag", "api", "--tag", "research", "--json"])
    data = json.loads(result.stdout)
    names = {p["name"] for p in data["projects"]}
    assert names == {"alpha"}


def test_list_shows_tags_in_json(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.project.tags = ["api"]
    save_project_manifest(proj / "project.toml", m)

    result = runner.invoke(app, ["list", "--json"])
    data = json.loads(result.stdout)
    assert data["projects"][0]["tags"] == ["api"]


def test_list_tag_filter_composes_with_phase(projects, make_project) -> None:
    from keel.manifest import load_project_manifest, save_project_manifest

    proj_a = make_project("alpha")
    proj_b = make_project("beta")
    m_a = load_project_manifest(proj_a / "project.toml")
    m_a.project.tags = ["api"]
    save_project_manifest(proj_a / "project.toml", m_a)
    m_b = load_project_manifest(proj_b / "project.toml")
    m_b.project.tags = ["api"]
    save_project_manifest(proj_b / "project.toml", m_b)
    (proj_b / ".keel" / "phase").write_text("implementing\n")

    result = runner.invoke(app, ["list", "--tag", "api", "--phase", "scoping", "--json"])
    data = json.loads(result.stdout)
    names = {p["name"] for p in data["projects"]}
    assert names == {"alpha"}
