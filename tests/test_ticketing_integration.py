"""Integration tests for ticketing commands (milestone/task add, start, done, cancel)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from keel.app import app
from keel.manifest import (
    load_milestones_manifest,
    load_project_manifest,
    save_project_manifest,
)
from keel.ticketing import get_provider_for_project
from keel.ticketing.mock import MockProvider


@pytest.fixture
def ticketing_project(make_project, monkeypatch):
    """Project with mock ticketing configured."""
    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.extensions["ticketing"] = {"provider": "mock"}
    save_project_manifest(proj / "project.toml", m)
    monkeypatch.chdir(proj)
    return proj


# --- get_provider_for_project tests ---


def test_get_provider_for_project_no_config(make_project) -> None:
    """No [extensions.ticketing] -> returns None."""
    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    assert get_provider_for_project(m) is None


def test_get_provider_for_project_unknown_provider(make_project) -> None:
    """[extensions.ticketing.provider] = "ghost" but no plugin installed -> None."""
    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.extensions["ticketing"] = {"provider": "ghost"}
    save_project_manifest(proj / "project.toml", m)
    m2 = load_project_manifest(proj / "project.toml")
    assert get_provider_for_project(m2) is None


def test_get_provider_for_project_loads_and_configures(make_project) -> None:
    """Configured provider is loaded and `.configure()` is called with the provider's subsection."""
    proj = make_project("foo")
    m = load_project_manifest(proj / "project.toml")
    m.extensions["ticketing"] = {"provider": "mock", "mock": {"key": "value"}}
    save_project_manifest(proj / "project.toml", m)
    m2 = load_project_manifest(proj / "project.toml")

    # Patch load_provider to return a fresh MockProvider for "mock"
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        provider = get_provider_for_project(m2)
    assert provider is fake
    assert ("configure", {"key": "value"}) in fake.calls


# --- milestone add tests ---


def test_milestone_add_pushes_to_provider(ticketing_project, monkeypatch) -> None:
    """When ticketing is configured + provider available, milestone add records ticket id."""
    proj = ticketing_project
    m = load_project_manifest(proj / "project.toml")
    m.extensions["ticketing"]["parent_id"] = "EPIC-1"
    save_project_manifest(proj / "project.toml", m)

    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        result = runner.invoke(
            app, ["milestone", "add", "m1", "--title", "X"], catch_exceptions=False
        )
    assert result.exit_code == 0
    saved = load_milestones_manifest(proj / "milestones.toml")
    assert "mock" in saved.milestones[0].tickets
    assert saved.milestones[0].tickets["mock"].startswith("MOCK-")
    assert any(c[0] == "create_milestone" for c in fake.calls)


def test_milestone_add_no_push_skips_provider(ticketing_project) -> None:
    """--no-push skips the provider call even when configured."""
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        result = runner.invoke(app, ["milestone", "add", "m1", "--title", "X", "--no-push"])
    assert result.exit_code == 0
    saved = load_milestones_manifest(proj / "milestones.toml")
    assert saved.milestones[0].tickets == {}
    assert not any(c[0] == "create_milestone" for c in fake.calls)


# --- task add tests ---


def test_task_add_pushes_with_parent_milestone_tickets(ticketing_project, monkeypatch) -> None:
    proj = ticketing_project
    m = load_project_manifest(proj / "project.toml")
    m.extensions["ticketing"]["parent_id"] = "EPIC-1"
    save_project_manifest(proj / "project.toml", m)

    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
        # milestone now has tickets = {"mock": "MOCK-1"} (or similar)
        result = runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"])
    assert result.exit_code == 0
    saved = load_milestones_manifest(proj / "milestones.toml")
    assert "mock" in saved.tasks[0].tickets


# --- milestone transition tests ---


def test_milestone_done_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "X"], catch_exceptions=False)
        runner.invoke(app, ["milestone", "start", "m1"])
        result = runner.invoke(app, ["milestone", "done", "m1"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "done" for args in transitions)


def test_milestone_start_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "X"], catch_exceptions=False)
        result = runner.invoke(app, ["milestone", "start", "m1"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "active" for args in transitions)


def test_milestone_cancel_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "X"], catch_exceptions=False)
        result = runner.invoke(app, ["milestone", "cancel", "m1", "-y"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "cancelled" for args in transitions)


# --- task transition tests ---


def test_task_start_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
        runner.invoke(
            app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False
        )
        result = runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "active" for args in transitions)


def test_task_done_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
        runner.invoke(
            app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False
        )
        runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)
        result = runner.invoke(app, ["task", "done", "t1"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "done" for args in transitions)


def test_task_cancel_transitions_provider(ticketing_project) -> None:
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
        runner.invoke(
            app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False
        )
        result = runner.invoke(app, ["task", "cancel", "t1", "-y"], catch_exceptions=False)
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert any(args[2] == "cancelled" for args in transitions)


# --- --no-push on transition tests ---


def test_milestone_start_no_push_skips_transition(ticketing_project) -> None:
    """--no-push on a transition command skips the provider.transition call."""
    proj = ticketing_project
    runner = CliRunner()
    fake = MockProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        runner.invoke(app, ["milestone", "add", "m1", "--title", "X"], catch_exceptions=False)
        result = runner.invoke(
            app, ["milestone", "start", "m1", "--no-push"], catch_exceptions=False
        )
    assert result.exit_code == 0
    transitions = [c for c in fake.calls if c[0] == "transition"]
    assert transitions == []


# --- provider failure tests ---


def test_milestone_add_provider_failure_does_not_fail_command(
    projects, ticketing_project,
) -> None:
    """If provider raises, the milestone is saved locally and the command exits 0 with a warning."""
    proj = ticketing_project
    runner = CliRunner()

    class BrokenProvider(MockProvider):
        def create_milestone(self, *args, **kwargs):
            raise RuntimeError("simulated provider failure")

    fake = BrokenProvider()
    with patch("keel.ticketing.load_provider", return_value=fake):
        result = runner.invoke(app, ["milestone", "add", "m1", "--title", "X"])
    # Even though provider failed, command should succeed and save locally.
    assert result.exit_code == 0
    saved = load_milestones_manifest(proj / "milestones.toml")
    assert len(saved.milestones) == 1
    assert saved.milestones[0].tickets == {}
    # Warning surfaced somewhere (stderr or stdout; out.warn goes to stderr)
    combined = result.stderr.lower() + result.stdout.lower()
    assert "ticket" in combined and "failed" in combined
