"""@hookable decorator and hook_event context manager — the command-side API.

Commands opt into hook firing by:

    @hookable("project.create")
    def cmd_new(ctx, ...):
        with hook_event("project.create", project=slug, payload={...}, out=out) as e:
            # ... do the work ...
            e.add_post_payload({"path": str(unit_dir)})  # optional post-only fields

The decorator records the command in the registry for `keel hooks list`.
The context manager fires ``entity.action.pre`` on entry, ``entity.action.post``
on clean exit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from keel.hooks.dispatcher import dispatch
from keel.hooks.types import HookEvent

if TYPE_CHECKING:
    from keel.output import Output


_HOOKABLE_COMMANDS: set[str] = set()


def hookable(event_name: str) -> Callable[[Callable], Callable]:
    """Decorator marking a command as firing pre/post events under `event_name`.

    Records the binding in a process-global set for introspection via
    `keel hooks list`. Does NOT wrap the function — the actual dispatch
    is the body's responsibility via `with hook_event(...)`.
    """

    def _decorate(fn: Callable) -> Callable:
        _HOOKABLE_COMMANDS.add(event_name)
        fn.__keel_hookable_event__ = event_name  # type: ignore[attr-defined]
        return fn

    return _decorate


def registered_events() -> set[str]:
    """Return the set of event names that any @hookable command has declared."""
    return set(_HOOKABLE_COMMANDS)


@dataclass
class _MutableEvent:
    """The event handle yielded by hook_event — lets the body add post-only payload fields."""

    name: str
    project: str | None
    deliverable: str | None
    positional_args: tuple[str, ...]
    pre_payload: dict[str, Any]
    post_extras: dict[str, Any] = field(default_factory=dict)

    def add_post_payload(self, fields: dict[str, Any]) -> None:
        """Merge additional fields into the post-event payload.

        Use this for values the body computes (e.g. resulting file path).
        Pre-event payload is unaffected.
        """
        self.post_extras.update(fields)


def _workspace_dir() -> Any:
    """Lazy resolution of PROJECTS_DIR to avoid import-time coupling."""
    from keel.workspace import projects_dir

    return projects_dir()


def _project_dir_for(project: str | None, deliverable: str | None) -> Any:
    """The unit dir corresponding to the scope, or None when no project."""
    if project is None:
        return None
    from keel.workspace import Scope

    return Scope(project=project, deliverable=deliverable).unit_dir


@contextmanager
def hook_event(
    event_base: str,
    *,
    project: str | None,
    deliverable: str | None = None,
    payload: dict[str, Any] | None = None,
    positional_args: tuple[str, ...] = (),
    out: Output,
    no_verify: bool = False,
) -> Iterator[_MutableEvent]:
    """Fire ``entity.action.pre`` on entry, ``entity.action.post`` on clean exit.

    *event_base* is a dotted ``"entity.action"`` string (e.g.
    ``"project.create"``).

    The yielded object exposes `add_post_payload(...)` so the body can
    augment the post payload with values it computed (e.g., resulting path).

    `no_verify=True` skips ALL pre-event subscribers (in-tree + plugin +
    user-script). Post-event subscribers always run on clean exit.
    """
    entity, action = event_base.split(".", 1)

    pre_payload = dict(payload or {})
    handle = _MutableEvent(
        name=event_base,
        project=project,
        deliverable=deliverable,
        positional_args=tuple(positional_args),
        pre_payload=pre_payload,
    )

    workspace = _workspace_dir()
    proj_dir = _project_dir_for(project, deliverable)

    if not no_verify:
        pre_event = HookEvent(
            entity=entity,
            action=action,
            phase="pre",
            project=project,
            deliverable=deliverable,
            payload=pre_payload,
            positional_args=handle.positional_args,
        )
        dispatch(pre_event, out=out, workspace_dir=workspace, project_dir=proj_dir)

    yield handle

    post_payload = {**pre_payload, **handle.post_extras}
    post_event = HookEvent(
        entity=entity,
        action=action,
        phase="post",
        project=project,
        deliverable=deliverable,
        payload=post_payload,
        positional_args=handle.positional_args,
    )
    dispatch(post_event, out=out, workspace_dir=workspace, project_dir=proj_dir)
