"""Tests for keel.hooks types."""

from __future__ import annotations

import pytest


def test_hook_event_construction() -> None:
    from keel.hooks import HookEvent

    event = HookEvent(
        entity="project",
        action="create",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={"description": "test"},
        positional_args=("foo",),
    )
    assert event.entity == "project"
    assert event.action == "create"
    assert event.phase == "pre"
    assert event.project == "foo"
    assert event.deliverable is None
    assert event.payload == {"description": "test"}
    assert event.positional_args == ("foo",)


def test_hook_event_is_frozen() -> None:
    """HookEvent must be immutable so subscribers can't mutate shared state."""
    from dataclasses import FrozenInstanceError

    from keel.hooks import HookEvent

    event = HookEvent(
        entity="project",
        action="create",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=(),
    )
    with pytest.raises(FrozenInstanceError):
        event.entity = "milestone"  # type: ignore[misc]


def test_hook_event_full_name() -> None:
    """full_name returns dotted 'entity.action.phase' format."""
    from keel.hooks import HookEvent

    pre = HookEvent(
        entity="project",
        action="create",
        phase="pre",
        project=None,
        deliverable=None,
        payload={},
        positional_args=(),
    )
    post = HookEvent(
        entity="milestone",
        action="status",
        phase="post",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=(),
    )
    assert pre.full_name == "project.create.pre"
    assert post.full_name == "milestone.status.post"


def test_hook_event_full_name_various_entities() -> None:
    """full_name works correctly across different entity/action combinations."""
    from keel.hooks import HookEvent

    cases = [
        ("deliverable", "add", "pre", "deliverable.add.pre"),
        ("decision", "create", "post", "decision.create.post"),
        ("tag", "rm", "pre", "tag.rm.pre"),
        ("task", "archive", "post", "task.archive.post"),
    ]
    for entity, action, phase, expected in cases:
        event = HookEvent(
            entity=entity,
            action=action,
            phase=phase,
            project="p",
            deliverable=None,
        )
        assert event.full_name == expected, f"expected {expected}, got {event.full_name}"


def test_hook_aborted_is_runtime_error() -> None:
    """HookAborted must be catchable as RuntimeError for natural error handling."""
    from keel.hooks import HookAborted

    err = HookAborted("blocked because reasons")
    assert isinstance(err, RuntimeError)
    assert str(err) == "blocked because reasons"
