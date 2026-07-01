"""Tests for the TicketProvider Protocol and Ticket dataclass."""

from keel.ticketing.base import Ticket, TicketProvider


def test_ticket_dataclass() -> None:
    t = Ticket(id="JIRA-1", url="https://example.com/JIRA-1")
    assert t.id == "JIRA-1"
    assert t.url == "https://example.com/JIRA-1"
    assert t.title is None
    assert t.status is None


def test_ticket_with_optionals() -> None:
    t = Ticket(id="X-1", url="u", title="Title", status="In Progress")
    assert t.title == "Title"
    assert t.status == "In Progress"


def test_ticket_is_frozen() -> None:
    import dataclasses

    t = Ticket(id="X-1", url="u")
    try:
        t.id = "Y-2"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Ticket should be frozen")


def test_ticket_provider_is_protocol() -> None:
    """TicketProvider should be a runtime-checkable Protocol."""

    # Any object with the right attributes/methods passes isinstance.
    class FakeProvider:
        name = "fake"

        def configure(self, config: dict) -> None:  # noqa: ARG002
            ...

        def create_milestone(self, milestone, scope) -> None:  # noqa: ANN001, ARG002
            ...

        def create_task(self, task, scope) -> None:  # noqa: ANN001, ARG002
            ...

        def transition(self, ticket_id, target_state) -> None:  # noqa: ARG002
            ...

        def fetch(self, ticket_id) -> None:  # noqa: ARG002
            ...

        def link_url(self, ticket_id) -> None:  # noqa: ARG002
            ...

    assert isinstance(FakeProvider(), TicketProvider)
