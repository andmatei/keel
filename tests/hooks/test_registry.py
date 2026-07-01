"""Tests for the in-tree subscriber registry."""

from __future__ import annotations


def test_subscribes_to_registers_function() -> None:
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()

    @subscribes_to("project.create.pre")
    def my_listener(event: HookEvent, *, out) -> None:
        pass

    subs = list(iter_matching_subscribers("project.create.pre"))
    assert len(subs) == 1
    assert subs[0] is my_listener


def test_subscribes_to_preserves_registration_order() -> None:
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()

    @subscribes_to("milestone.status.post")
    def first(event: HookEvent, *, out) -> None:
        pass

    @subscribes_to("milestone.status.post")
    def second(event: HookEvent, *, out) -> None:
        pass

    subs = list(iter_matching_subscribers("milestone.status.post"))
    assert subs == [first, second]


def test_iter_subscribers_empty_for_unknown_event() -> None:
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()
    assert list(iter_matching_subscribers("project.unknown.pre")) == []


def test_subscribes_to_rejects_single_segment() -> None:
    """Patterns must have at least 2 dotted segments."""
    import pytest

    from keel.hooks import subscribes_to
    from keel.hooks.registry import _clear_registry

    _clear_registry()

    with pytest.raises(ValueError, match="must have at least 2 dotted segments"):

        @subscribes_to("new")  # only one segment
        def bad(event, *, out) -> None:
            pass


def test_glob_match() -> None:
    """A glob pattern like '*.status.post' matches any entity."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()

    @subscribes_to("*.status.post")
    def wildcard_listener(event: HookEvent, *, out) -> None:
        pass

    subs = list(iter_matching_subscribers("milestone.status.post"))
    assert len(subs) == 1
    assert subs[0] is wildcard_listener


def test_exact_match_before_glob() -> None:
    """Exact-match subscribers are yielded before glob-match subscribers."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()

    @subscribes_to("*.status.post")
    def glob_listener(event: HookEvent, *, out) -> None:
        pass

    @subscribes_to("milestone.status.post")
    def exact_listener(event: HookEvent, *, out) -> None:
        pass

    subs = list(iter_matching_subscribers("milestone.status.post"))
    assert subs == [exact_listener, glob_listener]


def test_no_match_returns_empty() -> None:
    """Subscribers for unrelated events are not returned."""
    from keel.hooks import HookEvent, subscribes_to
    from keel.hooks.registry import _clear_registry, iter_matching_subscribers

    _clear_registry()

    @subscribes_to("project.create.pre")
    def unrelated(event: HookEvent, *, out) -> None:
        pass

    assert list(iter_matching_subscribers("milestone.status.post")) == []


def test_iter_in_tree_subscribers_alias() -> None:
    """iter_in_tree_subscribers is a backward-compat alias for iter_matching_subscribers."""
    from keel.hooks.registry import iter_in_tree_subscribers, iter_matching_subscribers

    assert iter_in_tree_subscribers is iter_matching_subscribers


def test_is_glob_helper() -> None:
    from keel.hooks.registry import _is_glob

    assert _is_glob("*.status.post") is True
    assert _is_glob("milestone.?.post") is True
    assert _is_glob("milestone.[abc].post") is True
    assert _is_glob("milestone.status.post") is False
