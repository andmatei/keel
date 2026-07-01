"""Tests for the MockProvider implementation."""

from keel.api import Milestone, Scope, Task
from keel.ticketing.base import TicketProvider
from keel.ticketing.mock import MockProvider


def test_mock_provider_satisfies_protocol() -> None:
    p = MockProvider()
    assert isinstance(p, TicketProvider)
    assert p.name == "mock"


def test_mock_provider_records_create_milestone() -> None:
    p = MockProvider()
    m = Milestone(id="m1", title="Foundation", status="planned")
    t = p.create_milestone(m, Scope(project="foo"))
    assert t.id.startswith("MOCK-")
    assert ("create_milestone", "m1", "Foundation") in p.calls


def test_mock_provider_records_create_task() -> None:
    p = MockProvider()
    task = Task(id="t1", milestone="m1", title="Set up", description="Initial config")
    t = p.create_task(task, Scope(project="foo"))
    assert t.id.startswith("MOCK-")
    assert ("create_task", "t1", "Set up", "m1") in p.calls


def test_mock_provider_transition_recorded() -> None:
    p = MockProvider()
    p.create_milestone(Milestone(id="m1", title="x"), Scope(project="foo"))
    ticket_id = "MOCK-1"
    p.transition(ticket_id, "active")
    assert ("transition", ticket_id, "active") in p.calls


def test_mock_provider_fetch_returns_recorded_ticket() -> None:
    p = MockProvider()
    t = p.create_milestone(Milestone(id="m1", title="x"), Scope(project="foo"))
    fetched = p.fetch(t.id)
    assert fetched.id == t.id


def test_mock_provider_link_url() -> None:
    p = MockProvider()
    url = p.link_url("MOCK-42")
    assert "MOCK-42" in url
