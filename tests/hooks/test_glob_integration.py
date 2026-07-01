"""End-to-end integration tests for glob pattern subscriptions.

These tests verify that glob patterns work across the full stack:
registry -> dispatcher -> hookable commands, with real CLI invocations.
"""

from __future__ import annotations

from typer.testing import CliRunner

from keel.app import app
from keel.hooks.registry import _clear_registry, subscribes_to
from keel.hooks.types import HookEvent

runner = CliRunner()


def test_glob_catches_all_status_events(projects, make_project, monkeypatch) -> None:
    """A *.status.post subscriber catches both milestone and task status changes."""
    _clear_registry()
    events: list[tuple[str, str | None]] = []

    @subscribes_to("*.status.post")
    def on_any_status(event: HookEvent, *, out) -> None:
        events.append((event.entity, event.payload.get("to")))

    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M"])
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"])
    runner.invoke(app, ["milestone", "start", "m1"], catch_exceptions=False)
    runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)

    assert ("milestone", "active") in events
    assert ("task", "active") in events


def test_glob_catches_all_create_events(projects, make_project, monkeypatch) -> None:
    """A *.create.post subscriber catches milestone.create and task.create."""
    _clear_registry()
    entities: list[str] = []

    @subscribes_to("*.create.post")
    def on_create(event: HookEvent, *, out) -> None:
        entities.append(event.entity)

    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False)

    assert "milestone" in entities
    assert "task" in entities


def test_glob_catches_all_post_events(projects, make_project, monkeypatch) -> None:
    """A *.*.post subscriber catches all post events from any command."""
    _clear_registry()
    events_seen: list[str] = []

    @subscribes_to("*.*.post")
    def on_any(event: HookEvent, *, out) -> None:
        events_seen.append(f"{event.entity}.{event.action}")

    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False)

    assert "milestone.create" in events_seen
    assert "task.create" in events_seen


def test_exact_and_glob_both_fire(projects, make_project, monkeypatch) -> None:
    """Both an exact subscriber and a glob subscriber fire for the same event, exact first."""
    _clear_registry()
    order: list[str] = []

    @subscribes_to("milestone.create.post")
    def exact(event: HookEvent, *, out) -> None:
        order.append("exact")

    @subscribes_to("*.create.post")
    def glob(event: HookEvent, *, out) -> None:
        order.append("glob")

    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)

    assert "exact" in order
    assert "glob" in order
    assert order.index("exact") < order.index("glob")


def test_glob_does_not_match_wrong_entity(projects, make_project, monkeypatch) -> None:
    """A milestone.*.post subscriber should NOT fire for task events."""
    _clear_registry()
    events: list[str] = []

    @subscribes_to("milestone.*.post")
    def on_milestone(event: HookEvent, *, out) -> None:
        events.append(event.entity)

    proj = make_project("foo")
    monkeypatch.chdir(proj)
    runner.invoke(app, ["milestone", "add", "m1", "--title", "M"], catch_exceptions=False)
    runner.invoke(app, ["task", "add", "t1", "--milestone", "m1", "--title", "T"], catch_exceptions=False)

    assert all(e == "milestone" for e in events)
