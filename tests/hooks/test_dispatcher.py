"""Tests for the central dispatcher."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_dispatcher_fires_in_tree_subscribers_in_order() -> None:
    """In-tree subscribers run in registration order."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    calls: list[str] = []

    @subscribes_to("project.create.pre")
    def first(event: HookEvent, *, out: Output) -> None:
        calls.append("first")

    @subscribes_to("project.create.pre")
    def second(event: HookEvent, *, out: Output) -> None:
        calls.append("second")

    event = HookEvent(
        entity="project",
        action="create",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=("foo",),
    )
    dispatch(event, out=Output(), workspace_dir=Path("/nonexistent"), project_dir=None)
    assert calls == ["first", "second"]


def test_dispatcher_pre_event_propagates_exceptions() -> None:
    """A pre-event subscriber raising HookAborted aborts the loop and propagates."""
    from keel.hooks import HookAborted, HookEvent, subscribes_to
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    calls: list[str] = []

    @subscribes_to("project.phase.pre")
    def first(event: HookEvent, *, out: Output) -> None:
        calls.append("first")
        raise HookAborted("blocked")

    @subscribes_to("project.phase.pre")
    def second(event: HookEvent, *, out: Output) -> None:
        calls.append("second")

    event = HookEvent(
        entity="project",
        action="phase",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={"from": "scoping", "to": "designing"},
        positional_args=("scoping", "designing"),
    )
    with pytest.raises(HookAborted, match="blocked"):
        dispatch(event, out=Output(), workspace_dir=Path("/nonexistent"), project_dir=None)
    assert calls == ["first"]  # second did NOT run


def test_dispatcher_pre_event_treats_arbitrary_exceptions_as_aborts() -> None:
    """ANY exception in pre subscriber aborts the command (buggy preflights still block)."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()

    @subscribes_to("project.create.pre")
    def buggy(event: HookEvent, *, out: Output) -> None:
        raise ValueError("oops, bug in preflight")

    event = HookEvent(
        entity="project",
        action="create",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=("foo",),
    )
    with pytest.raises(ValueError, match="oops, bug"):
        dispatch(event, out=Output(), workspace_dir=Path("/nonexistent"), project_dir=None)


def test_dispatcher_post_event_swallows_all_exceptions(capsys) -> None:
    """Post subscribers raising anything are caught — command already succeeded."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    calls: list[str] = []

    @subscribes_to("project.create.post")
    def broken(event: HookEvent, *, out: Output) -> None:
        raise ValueError("post-hook bug")

    @subscribes_to("project.create.post")
    def healthy(event: HookEvent, *, out: Output) -> None:
        calls.append("healthy")

    event = HookEvent(
        entity="project",
        action="create",
        phase="post",
        project="foo",
        deliverable=None,
        payload={"path": "/x"},
        positional_args=("foo",),
    )
    # Must NOT raise
    dispatch(event, out=Output(), workspace_dir=Path("/nonexistent"), project_dir=None)
    # Subsequent subscriber still ran
    assert calls == ["healthy"]


def test_dispatcher_fires_user_scripts_after_in_tree(tmp_path: Path, make_executable_script) -> None:
    """User scripts fire after in-tree subscribers, workspace before project."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()

    order_log = tmp_path / "order.log"
    workspace_dir = tmp_path / "ws"
    project_dir = tmp_path / "proj"
    (workspace_dir / ".keel" / "hooks").mkdir(parents=True)
    (project_dir / ".keel" / "hooks").mkdir(parents=True)

    @subscribes_to("project.create.post")
    def in_tree(event: HookEvent, *, out: Output) -> None:
        with order_log.open("a") as f:
            f.write("in-tree\n")

    make_executable_script(
        workspace_dir / ".keel" / "hooks" / "project.create.post",
        f'#!/usr/bin/env bash\necho "workspace" >> {order_log}\n',
    )
    make_executable_script(
        project_dir / ".keel" / "hooks" / "project.create.post",
        f'#!/usr/bin/env bash\necho "project" >> {order_log}\n',
    )

    event = HookEvent(
        entity="project",
        action="create",
        phase="post",
        project="foo",
        deliverable=None,
        payload={"path": str(project_dir)},
        positional_args=("foo",),
    )
    dispatch(event, out=Output(), workspace_dir=workspace_dir, project_dir=project_dir)

    assert order_log.read_text().splitlines() == ["in-tree", "workspace", "project"]


def test_dispatcher_no_subscribers_is_silent() -> None:
    """An event with no subscribers fires silently — no error, no warning."""
    from keel.hooks import HookEvent
    from keel.hooks.dispatcher import dispatch
    from keel.hooks.registry import _clear_registry
    from keel.output import Output

    _clear_registry()
    event = HookEvent(
        entity="misc",
        action="nothing-listens",
        phase="post",
        project=None,
        deliverable=None,
        payload={},
        positional_args=(),
    )
    dispatch(event, out=Output(), workspace_dir=Path("/nonexistent"), project_dir=None)
