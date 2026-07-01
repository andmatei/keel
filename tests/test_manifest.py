"""Tests for manifest schema and TOML I/O."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from keel.manifest import (
    Milestone,
    MilestonesManifest,
    ProjectManifest,
    ProjectMeta,
    RepoSpec,
    Task,
    load_milestones_manifest,
    load_project_manifest,
    save_milestones_manifest,
    save_project_manifest,
)


def test_repo_spec_minimal() -> None:
    spec = RepoSpec(remote="git@github.com:org/repo.git", worktree="code")
    assert spec.remote == "git@github.com:org/repo.git"
    assert spec.worktree == "code"
    assert spec.local_hint is None
    assert spec.branch_prefix is None


def test_repo_spec_full() -> None:
    spec = RepoSpec(
        remote="git@github.com:org/repo.git",
        local_hint="~/repo",
        worktree="code-repo",
        branch_prefix="andrei/foo-repo",
    )
    assert spec.local_hint == "~/repo"
    assert spec.branch_prefix == "andrei/foo-repo"


def test_repo_spec_rejects_empty_remote() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="", worktree="code")


def test_repo_spec_rejects_absolute_worktree() -> None:
    """Worktree must be a relative subdir name, not an absolute path."""
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@github.com:org/repo.git", worktree="/absolute/path")


def test_project_manifest_minimal() -> None:
    m = ProjectManifest(project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 27)))
    assert m.project.name == "foo"
    assert m.repos == []


def test_project_manifest_with_repos() -> None:
    m = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 27)),
        repos=[RepoSpec(remote="git@github.com:org/r.git", worktree="code")],
    )
    assert len(m.repos) == 1


def test_project_manifest_roundtrip(tmp_path) -> None:
    path = tmp_path / "project.toml"
    original = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 27)),
        repos=[
            RepoSpec(
                remote="git@github.com:org/r.git",
                local_hint="~/r",
                worktree="code",
                branch_prefix="me/foo",
            )
        ],
    )
    save_project_manifest(path, original)
    loaded = load_project_manifest(path)
    assert loaded == original
    # Lock on-disk format: native TOML date, not a quoted string
    text = path.read_text()
    assert "created = 2026-04-27" in text
    assert 'created = "2026-04-27"' not in text


def test_project_manifest_load_rejects_bad_schema(tmp_path) -> None:
    path = tmp_path / "project.toml"
    path.write_text('[project]\nname = "foo"\n')  # missing description and created
    with pytest.raises(ValidationError):
        load_project_manifest(path)


def test_repo_spec_rejects_worktree_with_slash() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree="sub/dir")


def test_repo_spec_rejects_worktree_dotdot() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree="..")


def test_repo_spec_rejects_worktree_dot() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree=".")


def test_repo_spec_rejects_worktree_with_backslash() -> None:
    with pytest.raises(ValidationError):
        RepoSpec(remote="git@e.com:o/r.git", worktree=r"sub\dir")


def test_repo_spec_accepts_normal_name() -> None:
    s = RepoSpec(remote="git@e.com:o/r.git", worktree="code")
    assert s.worktree == "code"
    s2 = RepoSpec(remote="git@e.com:o/r.git", worktree="code-foo")
    assert s2.worktree == "code-foo"


def test_project_manifest_extensions_default_empty() -> None:
    m = ProjectManifest(project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)))
    assert m.extensions == {}


def test_project_manifest_extensions_round_trip(tmp_path) -> None:
    """Plugin-namespaced config under extensions survives load/save."""
    path = tmp_path / "project.toml"
    original = ProjectManifest(
        project=ProjectMeta(name="foo", description="d", created=date(2026, 4, 29)),
        extensions={
            "ticketing": {
                "jira": {
                    "instance_url": "https://example.atlassian.net",
                    "project_key": "FOO",
                    "epic_id": "FOO-1234",
                }
            }
        },
    )
    save_project_manifest(path, original)
    loaded = load_project_manifest(path)
    assert loaded.extensions["ticketing"]["jira"]["epic_id"] == "FOO-1234"
    assert loaded.extensions == original.extensions


def test_project_manifest_unknown_top_level_still_rejected(tmp_path) -> None:
    """extra='forbid' still rejects unknown top-level keys (only `extensions` is open)."""
    path = tmp_path / "bad.toml"
    path.write_text(
        '[project]\nname = "foo"\ndescription = "d"\ncreated = 2026-04-29\n[bogus]\nfoo = "bar"\n'
    )
    with pytest.raises(ValidationError):
        load_project_manifest(path)


def test_milestone_minimal() -> None:
    m = Milestone(id="m1", title="Foundation")
    assert m.id == "m1"
    assert m.status == "planned"
    assert m.tickets == {}


def test_milestone_with_parent() -> None:
    m = Milestone(id="sub-m1", title="Sub work", parent="m1")
    assert m.parent == "m1"


def test_milestone_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Milestone(id="m1", title="t", status="bogus")


def test_milestone_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        Milestone(id="", title="t")


def test_task_minimal() -> None:
    t = Task(id="t1", milestone="m1", title="Set up")
    assert t.status == "planned"
    assert t.depends_on == []
    assert t.branch is None


def test_task_with_dependencies() -> None:
    t = Task(id="t2", milestone="m1", title="x", depends_on=["t1"])
    assert t.depends_on == ["t1"]


def test_milestones_manifest_minimal() -> None:
    m = MilestonesManifest()
    assert m.milestones == []
    assert m.tasks == []


def test_milestones_manifest_round_trip(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    original = MilestonesManifest(
        milestones=[
            Milestone(id="m1", title="Foundation", status="active"),
            Milestone(id="m2", title="Sub work", parent="m1"),
        ],
        tasks=[
            Task(id="t1", milestone="m1", title="Set up", status="done", branch="me/keel-m1-t1"),
            Task(
                id="t2",
                milestone="m1",
                title="Add models",
                depends_on=["t1"],
                branch="me/keel-m1-t2",
            ),
        ],
    )
    save_milestones_manifest(path, original)
    loaded = load_milestones_manifest(path)
    assert loaded == original


def test_milestones_manifest_load_missing_file_returns_empty(tmp_path) -> None:
    """If milestones.toml doesn't exist, load returns an empty manifest (not an error)."""
    path = tmp_path / "milestones.toml"
    m = load_milestones_manifest(path)
    assert m.milestones == []
    assert m.tasks == []


def test_milestones_tickets_round_trip(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    original = MilestonesManifest(
        milestones=[Milestone(id="m1", title="X", tickets={"jira": "CLOUDP-123"})],
        tasks=[Task(id="t1", milestone="m1", title="Y", tickets={"jira": "CLOUDP-456"})],
    )
    save_milestones_manifest(path, original)
    loaded = load_milestones_manifest(path)
    assert loaded.milestones[0].tickets == {"jira": "CLOUDP-123"}
    assert loaded.tasks[0].tickets == {"jira": "CLOUDP-456"}


def test_milestones_empty_tickets_omitted_from_toml(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    save_milestones_manifest(
        path,
        MilestonesManifest(milestones=[Milestone(id="m1", title="X")]),
    )
    text = path.read_text()
    assert "tickets" not in text
    loaded = load_milestones_manifest(path)
    assert loaded.milestones[0].tickets == {}


def test_milestones_none_description_omitted_from_toml(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    original = MilestonesManifest(
        milestones=[Milestone(id="m1", title="X")],
        tasks=[Task(id="t1", milestone="m1", title="Y")],
    )
    save_milestones_manifest(path, original)
    text = path.read_text()
    assert "description" not in text
    loaded = load_milestones_manifest(path)
    assert loaded.milestones[0].description is None
    assert loaded.tasks[0].description is None


def test_milestones_empty_depends_on_omitted_from_toml(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    save_milestones_manifest(
        path,
        MilestonesManifest(tasks=[Task(id="t1", milestone="m1", title="X")]),
    )
    text = path.read_text()
    assert "depends_on" not in text


def test_project_meta_lifecycle_defaults_to_default() -> None:
    """ProjectMeta picks 'default' when the lifecycle field is omitted."""
    m = ProjectMeta(name="foo", description="x", created=date(2026, 5, 1))
    assert m.lifecycle == "default"


def test_project_meta_lifecycle_custom_value() -> None:
    m = ProjectMeta(name="foo", description="x", created=date(2026, 5, 1), lifecycle="research")
    assert m.lifecycle == "research"


def test_project_manifest_lifecycle_round_trip(tmp_path) -> None:
    """The lifecycle field round-trips through the TOML save/load cycle."""
    path = tmp_path / "project.toml"
    original = ProjectManifest(
        project=ProjectMeta(
            name="foo", description="x", created=date(2026, 5, 1), lifecycle="research"
        ),
        repos=[],
    )
    save_project_manifest(path, original)
    loaded = load_project_manifest(path)
    assert loaded.project.lifecycle == "research"


def test_project_manifest_pre_v1_no_lifecycle_field(tmp_path) -> None:
    """An existing TOML without [project] lifecycle = ... still loads (defaults to 'default')."""
    path = tmp_path / "project.toml"
    path.write_text(
        """
[project]
name = "foo"
description = "x"
created = 2026-05-01
""".strip()
    )
    m = load_project_manifest(path)
    assert m.project.lifecycle == "default"


def test_project_meta_gains_shared_worktree() -> None:
    """ProjectMeta gains the field previously on DeliverableMeta."""
    from datetime import date

    from keel.manifest import ProjectMeta

    m = ProjectMeta(name="x", description="d", created=date(2026, 5, 5), shared_worktree=True)
    assert m.shared_worktree is True


def test_project_meta_shared_worktree_default_false() -> None:
    from datetime import date

    from keel.manifest import ProjectMeta

    m = ProjectMeta(name="x", description="d", created=date(2026, 5, 5))
    assert m.shared_worktree is False


def test_project_manifest_shared_worktree_excludes_repos(tmp_path) -> None:
    """If shared_worktree=True, repos must be empty (rule moved from DeliverableManifest)."""
    from datetime import date

    import pytest
    from pydantic import ValidationError

    from keel.manifest import ProjectManifest, ProjectMeta, RepoSpec

    with pytest.raises(ValidationError):
        ProjectManifest(
            project=ProjectMeta(
                name="x", description="d", created=date(2026, 5, 5), shared_worktree=True
            ),
            repos=[RepoSpec(remote="r", worktree="w")],
        )
