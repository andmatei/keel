"""Tests for hook events fired by milestone commands."""

from __future__ import annotations

from typer.testing import CliRunner

from keel.app import app
from keel.hooks import HookEvent, subscribes_to
from keel.hooks.registry import _clear_registry

runner = CliRunner()


def _add_milestone(proj_dir, milestone_id="m1", title="Foundation"):
    """Helper to create a milestone in the project."""
    runner.invoke(app, ["milestone", "add", milestone_id, "--title", title])


def test_milestone_add_fires_create_pre_and_post(projects, make_project, monkeypatch) -> None:
    """milestone add fires milestone.create.pre and milestone.create.post."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)

    fired: list[str] = []

    @subscribes_to("milestone.create.pre")
    def on_pre(event: HookEvent, **kwargs) -> None:
        fired.append(event.full_name)

    @subscribes_to("milestone.create.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        fired.append(event.full_name)

    result = runner.invoke(
        app, ["milestone", "add", "m1", "--title", "Foundation"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.stderr
    assert "milestone.create.pre" in fired
    assert "milestone.create.post" in fired


def test_milestone_start_fires_status_post(projects, make_project, monkeypatch) -> None:
    """milestone start fires milestone.status.post with correct from/to/command."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone(proj)

    captured: list[dict] = []

    @subscribes_to("milestone.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["milestone", "start", "m1"], catch_exceptions=False)
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["from"] == "planned"
    assert captured[0]["to"] == "active"
    assert captured[0]["command"] == "start"


def test_milestone_done_fires_status_post(projects, make_project, monkeypatch) -> None:
    """milestone done fires milestone.status.post with from=active, to=done."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone(proj)
    runner.invoke(app, ["milestone", "start", "m1"])

    captured: list[dict] = []

    @subscribes_to("milestone.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["milestone", "done", "m1"], catch_exceptions=False)
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["from"] == "active"
    assert captured[0]["to"] == "done"
    assert captured[0]["command"] == "done"


def test_milestone_cancel_fires_status_post(projects, make_project, monkeypatch) -> None:
    """milestone cancel fires milestone.status.post with to=cancelled."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone(proj)

    captured: list[dict] = []

    @subscribes_to("milestone.status.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["milestone", "cancel", "m1", "-y"], catch_exceptions=False)
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["to"] == "cancelled"
    assert captured[0]["command"] == "cancel"


def test_milestone_rm_fires_rm_post(projects, make_project, monkeypatch) -> None:
    """milestone rm fires milestone.rm.post with id."""
    _clear_registry()
    proj = make_project("foo")
    monkeypatch.chdir(proj)
    _add_milestone(proj)
    runner.invoke(app, ["milestone", "cancel", "m1", "-y"])

    captured: list[dict] = []

    @subscribes_to("milestone.rm.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(app, ["milestone", "rm", "m1", "-y"], catch_exceptions=False)
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["id"] == "m1"
