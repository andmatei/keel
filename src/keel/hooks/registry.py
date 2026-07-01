"""In-tree subscriber registry.

Built-in keel modules call ``@subscribes_to("entity.action.phase")`` at
import time to register themselves.  Patterns may contain shell-style
globs (``*``, ``?``, ``[seq]``) matched via :func:`fnmatch.fnmatch`.

The registry is process-global; tests reset it between runs via
``_clear_registry()``.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keel.hooks.types import HookEvent


Subscriber = Callable[["HookEvent"], None]
"""A subscriber is a callable receiving HookEvent + Output kwarg. See dispatcher."""


_REGISTRY: dict[str, list[Subscriber]] = {}


def _is_glob(pattern: str) -> bool:
    """Return True if *pattern* contains glob meta-characters."""
    return any(ch in pattern for ch in ("*", "?", "["))


def subscribes_to(pattern: str) -> Callable[[Subscriber], Subscriber]:
    """Decorator: register an in-tree subscriber for an event pattern.

    *pattern* must have at least two dotted segments (e.g.
    ``"project.create.pre"``, ``"*.status.post"``).  Glob characters
    ``*``, ``?``, and ``[seq]`` are supported and matched via
    :func:`fnmatch.fnmatch` at dispatch time.

    The decorated function receives the HookEvent and an Output kwarg,
    and returns None.  It may raise HookAborted (pre-events only) to abort.
    """
    # Replace glob chars with a placeholder letter so we can count real segments.
    _sanitised = pattern.replace("*", "x").replace("?", "x").replace("[", "x").replace("]", "x")
    if len(_sanitised.split(".")) < 2:
        raise ValueError(
            f"event pattern '{pattern}' must have at least 2 dotted segments "
            f"(e.g. 'entity.action.phase')"
        )

    def _register(fn: Subscriber) -> Subscriber:
        _REGISTRY.setdefault(pattern, []).append(fn)
        return fn

    return _register


def iter_matching_subscribers(event_full_name: str) -> Iterator[Subscriber]:
    """Yield subscribers whose pattern matches *event_full_name*.

    Exact-match subscribers are yielded first (in registration order),
    followed by glob-match subscribers (in registration order).
    """
    glob_matches: list[Subscriber] = []

    for pattern, subscribers in _REGISTRY.items():
        if pattern == event_full_name:
            yield from subscribers
        elif _is_glob(pattern) and fnmatch.fnmatch(event_full_name, pattern):
            glob_matches.extend(subscribers)

    yield from glob_matches


# Backward-compat alias kept during migration.
iter_in_tree_subscribers = iter_matching_subscribers


def _clear_registry() -> None:
    """Test-only: empty the registry. Not part of the public API."""
    _REGISTRY.clear()
