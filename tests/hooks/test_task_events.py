"""Tests for hook events fired by task commands."""

from __future__ import annotations

from typer.testing import CliRunner

from keel.app import app
from keel.hooks import HookEvent, subscribes_to
from keel.hooks.registry import _clear_registry

runner = CliRunner()


def _add_milestone(milestone_id="m1", title="Foundation"):
    """Helper to create a milestone in the project."""
    runner.invoke(app, ["milestone", "add", milestone_id, "--title", title])


def _start_milestone(milestone_id="m1"):
    """Helper to start a milestone."""
    runner.invoke(app, ["milestone", "start", milestone_id])


def _add_task(task_id="t1", milestone="m1", title="First task"):
    """Helper to add a task."""
    runner.invoke(app, ["task", "add", task_id, "--milestone", milestone, "--title", title])


def test_task_add_fires_create_post(projects, make_project, monkeypatch) -> None:
    """task add fires task.create.post with id and milestone."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone()

    captured: list[dict] = []

    @subscribes_to("task.create.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(
        app, ["task", "add", "t1", "--milestone", "m1", "--title", "First task"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["id"] == "t1"
    assert captured[0]["milestone"] == "m1"


def test_task_start_fires_status_post(projects, make_project, monkeypatch) -> None:
    """task start fires task.status.post with from=planned, to=active, command=start."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone()
    _start_milestone()
    _add_task()

    captured: list[dict] = []

    @subscribes_to("task.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["task", "start", "t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["from"] == "planned"
    assert captured[0]["to"] == "active"
    assert captured[0]["command"] == "start"


def test_task_done_fires_status_post(projects, make_project, monkeypatch) -> None:
    """task done fires task.status.post with to=done, command=done."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone()
    _start_milestone()
    _add_task()
    runner.invoke(app, ["task", "start", "t1"])

    captured: list[dict] = []

    @subscribes_to("task.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["task", "done", "t1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["to"] == "done"
    assert captured[0]["command"] == "done"


def test_task_cancel_fires_status_post(projects, make_project, monkeypatch) -> None:
    """task cancel fires task.status.post with to=cancelled, command=cancel."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone()
    _add_task()

    captured: list[dict] = []

    @subscribes_to("task.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(
        app, ["task", "cancel", "t1", "-y"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["to"] == "cancelled"
    assert captured[0]["command"] == "cancel"


def test_task_move_fires_move_post(projects, make_project, monkeypatch) -> None:
    """task move fires task.move.post with from_milestone and to_milestone."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone("m1", "Foundation")
    _add_milestone("m2", "Extension")
    _add_task("t1", "m1", "First task")

    captured: list[dict] = []

    @subscribes_to("task.move.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(
        app, ["task", "move", "t1", "--milestone", "m2"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert captured[0]["from_milestone"] == "m1"
    assert captured[0]["to_milestone"] == "m2"
