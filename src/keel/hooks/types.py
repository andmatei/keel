"""HookEvent dataclass and HookAborted exception."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class HookEvent:
    """A single hook event firing.

    Events use a dotted namespace: ``entity.action.phase``.

    Attributes are immutable so a misbehaving subscriber can't corrupt
    state for downstream subscribers.
    """

    entity: str
    """The resource type the event targets (e.g., 'project', 'milestone',
    'deliverable', 'decision', 'task', 'tag')."""

    action: str
    """The operation performed on the entity (e.g., 'create', 'rm', 'status',
    'phase', 'move', 'rename', 'archive', 'restore', 'add')."""

    phase: Literal["pre", "post"]
    """Whether this event fires before or after the command's work."""

    project: str | None
    """Project slug, or None for events not scoped to a project."""

    deliverable: str | None
    """Deliverable slug, or None for project-scoped events."""

    payload: dict[str, Any] = field(default_factory=dict)
    """Event-specific structured data. Always a dict (may be empty)."""

    positional_args: tuple[str, ...] = ()
    """High-value identifiers passed as argv to user scripts. Stable, additive."""

    @property
    def full_name(self) -> str:
        """Dotted event name, e.g. 'project.create.pre' or 'milestone.status.post'."""
        return f"{self.entity}.{self.action}.{self.phase}"


class HookAborted(RuntimeError):
    """Raised by a pre-hook subscriber to abort the command.

    Subscribers may raise this to block a transition (e.g., preflight checks
    that find a blocker). The dispatcher catches and surfaces the message.
    """
