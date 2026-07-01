"""Tests for hook events fired by deliverable commands."""

from __future__ import annotations

from typer.testing import CliRunner

from keel.app import app
from keel.hooks import HookEvent, subscribes_to
from keel.hooks.registry import _clear_registry

runner = CliRunner()


def test_deliverable_rm_fires_rm_post(projects, make_project, make_deliverable, monkeypatch) -> None:
    """deliverable rm fires deliverable.rm.post with name in payload."""
    _clear_registry()
    proj = make_project("foo")
    make_deliverable(project_name="foo", name="alpha", description="d")
    monkeypatch.chdir(proj)

    captured: list[dict] = []

    @subscribes_to("deliverable.rm.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(
        app, ["deliverable", "rm", "alpha", "--project", "foo", "-y"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["name"] == "alpha"


def test_deliverable_rename_fires_rename_post(
    projects, make_project, make_deliverable, monkeypatch
) -> None:
    """deliverable rename fires deliverable.rename.post with old_name and new_name."""
    _clear_registry()
    proj = make_project("foo")
    make_deliverable(project_name="foo", name="alpha", description="d")
    monkeypatch.chdir(proj)

    captured: list[dict] = []

    @subscribes_to("deliverable.rename.post")
    def on_post(event: HookEvent, **kwargs) -> None:
        captured.append(dict(event.payload))

    result = runner.invoke(
        app,
        ["deliverable", "rename", "alpha", "beta", "--project", "foo", "-y"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stderr
    assert len(captured) == 1
    assert captured[0]["old_name"] == "alpha"
    assert captured[0]["new_name"] == "beta"
