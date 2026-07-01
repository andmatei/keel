"""Tests for JiraProvider — the TicketProvider implementation (v0.0.2)."""

import json as _json

import pytest
import respx
from httpx import Response
from keel.api import (
    Milestone,
    MilestonesManifest,
    ProjectManifest,
    ProjectMeta,
    Task,
    Ticket,
    TicketProvider,
    save_milestones_manifest,
    save_project_manifest,
)
from keel.workspace import Scope

from keel_jira.client import JiraAPIError
from keel_jira.config import JiraCredentialsMissing
from keel_jira.provider import JiraProvider

# ----- helpers ---------------------------------------------------------------


def _config_block(**overrides):
    base = {"url": "https://acme.atlassian.net", "project_key": "PROJ"}
    base.update(overrides)
    return base


def _configured_provider(jira_env, **config_overrides):
    p = JiraProvider()
    p.configure(_config_block(**config_overrides))
    return p


def _set_parent_id_extension(project_dir, parent_id: str) -> None:
    """Rewrite the project's manifest with [extensions.ticketing.parent_id]."""
    from datetime import date

    save_project_manifest(
        project_dir / "project.toml",
        ProjectManifest(
            project=ProjectMeta(
                name=project_dir.name,
                description="test",
                created=date(2026, 5, 5),
            ),
            repos=[],
            extensions={"ticketing": {"parent_id": parent_id}},
        ),
    )


# ----- protocol / config sanity ---------------------------------------------


def test_provider_satisfies_protocol(jira_env) -> None:
    p = _configured_provider(jira_env)
    assert isinstance(p, TicketProvider)
    assert p.name == "jira"


def test_unconfigured_provider_raises(jira_env) -> None:
    p = JiraProvider()
    milestone = Milestone(id="m1", title="x")
    scope = Scope(project="foo")
    with pytest.raises(JiraCredentialsMissing):
        p.create_milestone(milestone, scope)


def test_configure_requires_credentials(monkeypatch) -> None:
    monkeypatch.delenv("KEEL_JIRA_EMAIL", raising=False)
    monkeypatch.delenv("KEEL_JIRA_TOKEN", raising=False)
    p = JiraProvider()
    with pytest.raises(JiraCredentialsMissing):
        p.configure(_config_block())


# ----- create_milestone -----------------------------------------------------


def test_create_milestone_with_typed_object(jira_env, make_project) -> None:
    make_project("foo")
    p = _configured_provider(jira_env)
    milestone = Milestone(id="m1", title="Foundation", description="The base.")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "1", "key": "PROJ-10"})
        )
        ticket = p.create_milestone(milestone, scope)

    assert isinstance(ticket, Ticket)
    assert ticket.id == "PROJ-10"
    assert ticket.url == "https://acme.atlassian.net/browse/PROJ-10"
    assert ticket.title == "Foundation"
    assert ticket.status == "To Do"

    payload = _json.loads(route.calls.last.request.read())
    assert payload["fields"]["issuetype"]["name"] == "Story"
    assert payload["fields"]["summary"] == "Foundation"
    # No parent_id configured on the manifest — issue is created at the project level.
    assert "parent" not in payload["fields"]


def test_create_milestone_uses_parent_id_extension(jira_env, make_project) -> None:
    proj = make_project("foo")
    _set_parent_id_extension(proj, "EPIC-1")

    p = _configured_provider(jira_env)
    milestone = Milestone(id="m1", title="Foundation")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "1", "key": "PROJ-10"})
        )
        p.create_milestone(milestone, scope)

    payload = _json.loads(route.calls.last.request.read())
    assert payload["fields"]["parent"] == {"key": "EPIC-1"}


def test_user_template_overrides_default(jira_env, make_project) -> None:
    make_project("foo")
    p = JiraProvider()
    p.configure(
        _config_block(
            templates={
                "milestone_summary": "[{{ milestone.id }}] {{ milestone.title }}",
            }
        )
    )

    milestone = Milestone(id="m1", title="Foundation")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "1", "key": "PROJ-11"})
        )
        ticket = p.create_milestone(milestone, scope)

    payload = _json.loads(route.calls.last.request.read())
    assert payload["fields"]["summary"] == "[m1] Foundation"
    # The Ticket's title reflects the rendered summary, not the raw milestone.title.
    assert ticket.title == "[m1] Foundation"


# ----- create_task ----------------------------------------------------------


def test_create_task_with_typed_object(jira_env, make_project) -> None:
    proj = make_project("foo")
    # Seed the milestones manifest with a parent that already has a ticket id.
    save_milestones_manifest(
        proj / "milestones.toml",
        MilestonesManifest(
            milestones=[Milestone(id="m1", title="Foundation", tickets={"jira": "PROJ-10"})],
            tasks=[],
        ),
    )
    p = _configured_provider(jira_env)
    task = Task(id="t1", milestone="m1", title="Set up CI", description="bootstrap")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "2", "key": "PROJ-20"})
        )
        ticket = p.create_task(task, scope)

    assert ticket.id == "PROJ-20"

    payload = _json.loads(route.calls.last.request.read())
    assert payload["fields"]["issuetype"]["name"] == "Sub-task"
    assert payload["fields"]["summary"] == "Set up CI"
    # Parent was looked up from the milestones manifest's tickets dict.
    assert payload["fields"]["parent"] == {"key": "PROJ-10"}
    # Default task_description template appends "— keel: `t1`".
    desc_text = payload["fields"]["description"]["content"][0]["content"][0]["text"]
    assert "bootstrap" in desc_text
    assert "t1" in desc_text


def test_create_task_no_parent_milestone(jira_env, make_project) -> None:
    """If the milestones manifest doesn't have the parent, no parent key is sent."""
    make_project("foo")
    p = _configured_provider(jira_env)
    task = Task(id="t1", milestone="m-missing", title="Loose")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "2", "key": "PROJ-21"})
        )
        p.create_task(task, scope)

    payload = _json.loads(route.calls.last.request.read())
    assert "parent" not in payload["fields"]


# ----- labels / custom fields -----------------------------------------------


def test_labels_and_custom_fields_are_rendered(jira_env, make_project) -> None:
    make_project("foo")
    p = JiraProvider()
    p.configure(
        _config_block(
            labels=["keel", "milestone-{{ milestone.id }}"],
            custom_fields={"customfield_10001": "{{ milestone.title }}"},
        )
    )
    milestone = Milestone(id="m1", title="Foundation")
    scope = Scope(project="foo")

    with respx.mock:
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue").mock(
            return_value=Response(201, json={"id": "1", "key": "PROJ-30"})
        )
        p.create_milestone(milestone, scope)

    payload = _json.loads(route.calls.last.request.read())
    assert payload["fields"]["labels"] == ["keel", "milestone-m1"]
    assert payload["fields"]["customfield_10001"] == "Foundation"


# ----- transition / fetch / link_url (unchanged) ----------------------------


def test_transition_finds_correct_id(jira_env) -> None:
    p = _configured_provider(jira_env)
    with respx.mock:
        respx.get("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(
                200,
                json={
                    "transitions": [
                        {"id": "11", "to": {"name": "In Progress"}},
                        {"id": "21", "to": {"name": "Done"}},
                    ]
                },
            )
        )
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(204)
        )
        p.transition("PROJ-10", "done")
    payload = _json.loads(route.calls.last.request.read())
    assert payload == {"transition": {"id": "21"}}


def test_transition_uses_status_map(jira_env) -> None:
    p = _configured_provider(
        jira_env,
        status_map={
            "planned": "Backlog",
            "active": "Selected for Dev",
            "done": "Released",
            "cancelled": "Won't Do",
        },
    )
    with respx.mock:
        respx.get("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(
                200,
                json={"transitions": [{"id": "31", "to": {"name": "Released"}}]},
            )
        )
        route = respx.post("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(204)
        )
        p.transition("PROJ-10", "done")
    payload = _json.loads(route.calls.last.request.read())
    assert payload == {"transition": {"id": "31"}}


def test_transition_status_match_is_case_insensitive(jira_env) -> None:
    p = _configured_provider(jira_env)
    with respx.mock:
        respx.get("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(
                200,
                json={"transitions": [{"id": "21", "to": {"name": "DONE"}}]},
            )
        )
        respx.post("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(204)
        )
        p.transition("PROJ-10", "done")  # status_map has "Done", API has "DONE"


def test_transition_no_matching_transition_raises(jira_env) -> None:
    p = _configured_provider(jira_env)
    with respx.mock:
        respx.get("https://acme.atlassian.net/rest/api/3/issue/PROJ-10/transitions").mock(
            return_value=Response(
                200,
                json={"transitions": [{"id": "11", "to": {"name": "In Progress"}}]},
            )
        )
        with pytest.raises(JiraAPIError) as exc:
            p.transition("PROJ-10", "done")
    assert "Done" in str(exc.value)


def test_fetch(jira_env) -> None:
    p = _configured_provider(jira_env)
    with respx.mock:
        respx.get("https://acme.atlassian.net/rest/api/3/issue/PROJ-10").mock(
            return_value=Response(
                200,
                json={
                    "key": "PROJ-10",
                    "fields": {"summary": "Foundation", "status": {"name": "In Progress"}},
                },
            )
        )
        ticket = p.fetch("PROJ-10")
    assert ticket.id == "PROJ-10"
    assert ticket.title == "Foundation"
    assert ticket.status == "In Progress"
    assert ticket.url == "https://acme.atlassian.net/browse/PROJ-10"


def test_link_url_no_network(jira_env) -> None:
    p = _configured_provider(jira_env)
    # No respx — must not call out.
    assert p.link_url("PROJ-99") == "https://acme.atlassian.net/browse/PROJ-99"
