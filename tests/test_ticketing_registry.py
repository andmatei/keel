"""Tests for the ticketing provider registry (entry-point loading)."""

from unittest.mock import MagicMock, patch

from keel.ticketing.registry import list_providers, load_provider


def test_load_provider_returns_none_when_not_found() -> None:
    with patch("keel.ticketing.registry.entry_points", return_value=[]):
        result = load_provider("nothing")
    assert result is None


def test_list_providers_empty() -> None:
    with patch("keel.ticketing.registry.entry_points", return_value=[]):
        result = list_providers()
    assert result == []


def test_load_provider_finds_registered() -> None:
    """When an entry point matches by name, load_provider instantiates it."""

    class FakeProvider:
        name = "fake"

        def configure(self, config) -> None:  # noqa: ANN001, ARG002
            pass

        def create_milestone(self, milestone, scope) -> None:  # noqa: ANN001, ARG002
            pass

        def create_task(self, task, scope) -> None:  # noqa: ANN001, ARG002
            pass

        def transition(self, ticket_id, target_state) -> None:  # noqa: ANN001, ARG002
            pass

        def fetch(self, ticket_id) -> None:  # noqa: ANN001, ARG002
            pass

        def link_url(self, ticket_id) -> None:  # noqa: ANN001, ARG002
            pass

    fake_ep = MagicMock()
    fake_ep.name = "fake"
    fake_ep.load.return_value = FakeProvider

    with patch("keel.ticketing.registry.entry_points", return_value=[fake_ep]):
        result = load_provider("fake")
    assert result is not None
    assert result.name == "fake"


def test_list_providers_returns_names() -> None:
    ep1 = MagicMock()
    ep1.name = "jira"
    ep2 = MagicMock()
    ep2.name = "github"
    with patch("keel.ticketing.registry.entry_points", return_value=[ep1, ep2]):
        result = list_providers()
    assert result == ["github", "jira"]  # sorted
