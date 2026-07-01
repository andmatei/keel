"""Tests for the @hookable decorator and hook_event context manager."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_hookable_registers_command_name() -> None:
    """@hookable records the event name on the function."""
    from keel.hooks.hookable import hookable, registered_events

    @hookable("project.create")
    def my_cmd():
        pass

    assert "project.create" in registered_events()
    assert getattr(my_cmd, "__keel_hookable_event__", None) == "project.create"


def test_hook_event_fires_pre_on_entry(monkeypatch, tmp_path: Path) -> None:
    """Entering the context manager fires the pre-event."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.hookable import hook_event
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    fired: list[str] = []

    @subscribes_to("project.create.pre")
    def pre(event: HookEvent, *, out: Output) -> None:
        fired.append(event.full_name)

    with hook_event(
        "project.create",
        project="foo",
        deliverable=None,
        payload={"description": "x"},
        positional_args=("foo",),
        out=Output(),
    ):
        pass  # body

    assert "project.create.pre" in fired


def test_hook_event_fires_post_on_clean_exit(monkeypatch, tmp_path: Path) -> None:
    """Clean exit fires post-event."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.hookable import hook_event
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    fired: list[str] = []

    @subscribes_to("project.create.post")
    def post(event: HookEvent, *, out: Output) -> None:
        fired.append(event.full_name)

    with hook_event(
        "project.create",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=("foo",),
        out=Output(),
    ):
        pass

    assert "project.create.post" in fired


def test_hook_event_skips_post_on_exception(monkeypatch, tmp_path: Path) -> None:
    """If the body raises, post-event does NOT fire."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.hookable import hook_event
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    fired: list[str] = []

    @subscribes_to("project.create.post")
    def post(event: HookEvent, *, out: Output) -> None:
        fired.append(event.full_name)

    with (
        pytest.raises(ValueError),
        hook_event(
            "project.create",
            project="foo",
            deliverable=None,
            payload={},
            positional_args=("foo",),
            out=Output(),
        ),
    ):
        raise ValueError("body failed")

    assert fired == []


def test_hook_event_post_payload_can_be_extended(monkeypatch, tmp_path: Path) -> None:
    """The event yielded by the context manager lets the body add post-only fields."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.hookable import hook_event
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))
    captured: list[dict] = []

    @subscribes_to("project.create.post")
    def post(event: HookEvent, *, out: Output) -> None:
        captured.append(dict(event.payload))

    with hook_event(
        "project.create",
        project="foo",
        deliverable=None,
        payload={"description": "x"},
        positional_args=("foo",),
        out=Output(),
    ) as ev:
        # body mutates the payload (via the helper method)
        ev.add_post_payload({"path": "/some/where"})

    assert captured == [{"description": "x", "path": "/some/where"}]


def test_no_verify_bypasses_pre_subscribers(monkeypatch, tmp_path: Path) -> None:
    """When no_verify=True, pre-event subscribers are skipped entirely."""
    from keel.hooks import HookAborted, HookEvent, subscribes_to
    from keel.hooks.hookable import hook_event
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path))

    @subscribes_to("project.create.pre")
    def always_block(event: HookEvent, *, out: Output) -> None:
        raise HookAborted("nope")

    # Without no_verify, this would raise
    with hook_event(
        "project.create",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=("foo",),
        out=Output(),
        no_verify=True,
    ):
        pass  # passes despite the pre-hook that would block
