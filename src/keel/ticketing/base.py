"""Ticketing plugin protocol.

Plugin authors implement TicketProvider; keel core uses it via the registry.
keel core ships zero real providers — only this protocol and a MockProvider
in keel.ticketing.mock for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from keel.manifest import Milestone, Task
    from keel.workspace import Scope


@dataclass(frozen=True)
class Ticket:
    """Provider-agnostic ticket reference.

    The `status` field contains the provider's status string. For real providers this is the
    native state name (e.g. Jira's 'In Progress'). For MockProvider it equals keel's neutral
    state ('planned', 'active', 'done', 'cancelled') by design — this makes mock-based tests
    easier to write and assert on.
    """

    id: str
    url: str
    title: str | None = None
    status: str | None = None


@runtime_checkable
class TicketProvider(Protocol):
    """Ticketing plugin protocol — typed-object based, no pre-rendered strings.

    A plugin package registers a TicketProvider via the `keel.ticket_providers`
    entry-point group. keel core uses this protocol; it never imports the
    plugin's internals.

    Plugins receive the keel domain objects directly and render their own
    payloads. keel-cli ships no shared template helper. To find the parent
    project ticket id, walk `scope.manifest_path` and read your plugin's
    config from `[extensions.ticketing.<name>]`.

    The neutral status names are: planned, active, done, cancelled.
    Each provider is responsible for mapping these to its native states
    (and back).
    """

    name: str
    """Provider name. MUST equal the entry-point name registered in
    `[project.entry-points."keel.ticket_providers"]`. keel uses this string
    both as the lookup key and as the value of `[extensions.ticketing.provider]`
    in `project.toml`."""

    def configure(self, config: dict) -> None:
        """Validate and store the [extensions.ticketing.<name>] config dict.

        Raises ValueError (or any exception) on bad config — keel does NOT catch it,
        so the user will see the failure immediately. This is intentional: a misconfigured
        provider should fail loud, not silently fall back to local-only mode.
        """
        ...

    def create_milestone(self, milestone: Milestone, scope: Scope) -> Ticket:
        """Create a ticket for the milestone.

        The returned `Ticket.id` is stored in `milestone.tickets[self.name]`
        by the caller.

        May raise on transport / auth failures. Keel wraps these in `safe_push`, which
        logs a warning and continues — the local manifest save is preserved.
        """
        ...

    def create_task(self, task: Task, scope: Scope) -> Ticket:
        """Create a ticket for the task.

        Same shape as `create_milestone`. To find the milestone's parent ticket id,
        walk `scope.manifest` → milestones → find_by_id(task.milestone) → tickets[self.name].

        Returns a `Ticket` with at minimum `id` and `url` populated. `title` and `status`
        are recommended but optional.

        May raise on transport / auth failures. Keel wraps these in `safe_push`, which
        logs a warning and continues — the local manifest save is preserved.
        """
        ...

    def transition(self, ticket_id: str, target_state: str) -> None:
        """Move a ticket to one of: 'planned', 'active', 'done', 'cancelled'.

        These are keel's neutral state names. Plugins are responsible for mapping them
        to provider-native states (e.g. Jira's 'To Do', 'In Progress', 'Done', 'Cancelled').
        Per-project overrides via [ticketing.status_map] are reserved for a future plan;
        plugins may accept a `status_map` key in the configure() dict.
        """
        ...

    def fetch(self, ticket_id: str) -> Ticket:
        """Re-read a ticket's state from the provider.

        Implementations SHOULD make a fresh request (not cache) when called via
        `keel * refresh` semantics. Used to detect drift between local manifest
        and the provider's source of truth.
        """
        ...

    def link_url(self, ticket_id: str) -> str:
        """Return a stable, clickable URL to view the ticket in the provider's UI.

        Pure function; should not require network. Used in CLI output and exports.
        """
        ...
