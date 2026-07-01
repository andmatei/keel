"""JiraProvider — implements `keel.api.TicketProvider`.

The plugin owns its own Jinja templating layer and reads typed
`Milestone`/`Task` objects + a `Scope` from keel core. The parent
project epic id is read from `[extensions.ticketing.parent_id]` on
the project's manifest; per-task parent milestone ticket ids come from
the milestones manifest's `tickets` dict (keyed by provider name).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keel.api import Ticket

from keel_jira.client import JiraAPIError, JiraClient
from keel_jira.config import JiraConfig, JiraCredentialsMissing
from keel_jira.templates import DEFAULT_TEMPLATES, make_env, render

if TYPE_CHECKING:
    from keel.manifest import Milestone, Task
    from keel.workspace import Scope


class JiraProvider:
    """A `TicketProvider` backed by Jira Cloud REST API v3.

    Lifecycle: keel calls `configure()` once with the parsed
    `[extensions.ticketing.jira]` block; subsequent calls (`create_milestone`,
    `transition`, etc.) hit the API.
    """

    name: str = "jira"

    def __init__(self) -> None:
        self._config: JiraConfig | None = None
        self._client: JiraClient | None = None
        self._env = make_env()

    def configure(self, config: dict) -> None:
        """Validate and store the [extensions.ticketing.jira] block.

        Reads credentials from KEEL_JIRA_EMAIL / KEEL_JIRA_TOKEN env vars.
        Raises if structural fields are invalid or credentials are missing.
        """
        cfg = JiraConfig.from_extension_block(config)
        # Credentials are guaranteed non-None by from_extension_block.
        assert cfg.email is not None
        assert cfg.token is not None
        self._config = cfg
        self._client = JiraClient(url=cfg.url, email=cfg.email, token=cfg.token)

    def create_milestone(self, milestone: Milestone, scope: Scope) -> Ticket:
        """Create an issue representing a milestone (typically a Story under an Epic)."""
        cfg, client = self._require_configured()
        ctx = self._build_context(milestone=milestone, scope=scope)
        summary = render(self._env, self._resolve_template("milestone_summary"), ctx)
        description = render(self._env, self._resolve_template("milestone_description"), ctx)
        labels = cfg.render_field(cfg.labels, ctx)
        custom_fields = cfg.render_field(cfg.custom_fields, ctx)
        parent_id = self._read_parent_id(scope)

        result = client.create_issue(
            project_key=cfg.project_key,
            issue_type=cfg.issue_type_milestone,
            summary=summary,
            description=description,
            parent_key=parent_id or None,
            labels=labels,
            custom_fields=custom_fields,
        )
        key = result["key"]
        return Ticket(
            id=key,
            url=client.link_url(key),
            title=summary,
            status=cfg.jira_status_for("planned"),
        )

    def create_task(self, task: Task, scope: Scope) -> Ticket:
        """Create an issue representing a task (typically a Sub-task under a Story)."""
        cfg, client = self._require_configured()

        # Find the parent milestone's ticket id from the scope's milestones manifest.
        from keel.api import find_milestone, load_milestones_manifest

        manifest = load_milestones_manifest(scope.milestones_manifest_path)
        parent_milestone = find_milestone(manifest, task.milestone)
        parent_ticket_id = parent_milestone.tickets.get(self.name) if parent_milestone else None

        ctx = self._build_context(task=task, milestone=parent_milestone, scope=scope)
        summary = render(self._env, self._resolve_template("task_summary"), ctx)
        description = render(self._env, self._resolve_template("task_description"), ctx)
        labels = cfg.render_field(cfg.labels, ctx)
        custom_fields = cfg.render_field(cfg.custom_fields, ctx)

        result = client.create_issue(
            project_key=cfg.project_key,
            issue_type=cfg.issue_type_task,
            summary=summary,
            description=description,
            parent_key=parent_ticket_id,
            labels=labels,
            custom_fields=custom_fields,
        )
        key = result["key"]
        return Ticket(
            id=key,
            url=client.link_url(key),
            title=summary,
            status=cfg.jira_status_for("planned"),
        )

    def transition(self, ticket_id: str, target_state: str) -> None:
        """Move an issue to the Jira status mapped from a keel neutral state.

        `target_state` is one of: 'planned', 'active', 'done', 'cancelled'.
        Resolves the right `transitions[].id` for the issue's current
        workflow position; raises `JiraAPIError` if no transition leads to
        the target status.
        """
        cfg, client = self._require_configured()
        target_status = cfg.jira_status_for(target_state)

        transitions = client.list_transitions(ticket_id)
        match = next(
            (
                t
                for t in transitions
                if t.get("to", {}).get("name", "").lower() == target_status.lower()
            ),
            None,
        )
        if match is None:
            available = [t.get("to", {}).get("name") for t in transitions]
            raise JiraAPIError(
                400,
                f"no transition leads to status '{target_status}' from issue {ticket_id} "
                f"(available: {available})",
            )
        client.transition_issue(ticket_id, match["id"])

    def fetch(self, ticket_id: str) -> Ticket:
        """Re-read an issue's current state from Jira."""
        _, client = self._require_configured()
        result = client.get_issue(ticket_id)
        fields = result.get("fields", {}) if isinstance(result, dict) else {}
        return Ticket(
            id=result.get("key", ticket_id),
            url=client.link_url(result.get("key", ticket_id)),
            title=fields.get("summary"),
            status=(fields.get("status") or {}).get("name"),
        )

    def link_url(self, ticket_id: str) -> str:
        """Return a clickable URL for the issue. Pure — no network call."""
        _, client = self._require_configured()
        return client.link_url(ticket_id)

    # ------- internals -------

    def _build_context(
        self,
        *,
        milestone: Milestone | None = None,
        task: Task | None = None,
        scope: Scope,
    ) -> dict:
        """Assemble the Jinja context shared by summary/description/labels/custom_fields."""
        ctx: dict = {
            "project": scope.project,
            "deliverable": scope.deliverable,
            "scope": scope,
        }
        if milestone is not None:
            ctx["milestone"] = milestone
            ctx["milestone_id"] = milestone.id
        if task is not None:
            ctx["task"] = task
            ctx["task_id"] = task.id
        return ctx

    def _resolve_template(self, key: str) -> str:
        """Return the user override for `key`, or the built-in default."""
        cfg = self._config
        if cfg is not None and cfg.templates.get(key):
            return cfg.templates[key]
        return DEFAULT_TEMPLATES[key]

    def _read_parent_id(self, scope: Scope) -> str | None:
        """Read [extensions.ticketing.parent_id] from the project manifest, if present.

        Returns None if the manifest can't be read or the key isn't set.
        """
        from keel.api import load_project_manifest

        try:
            pm = load_project_manifest(scope.manifest_path)
        except Exception:
            return None
        ticketing = pm.extensions.get("ticketing", {}) if pm.extensions else {}
        if not isinstance(ticketing, dict):
            return None
        parent = ticketing.get("parent_id")
        return parent if isinstance(parent, str) and parent else None

    def _require_configured(self) -> tuple[JiraConfig, JiraClient]:
        if self._config is None or self._client is None:
            raise JiraCredentialsMissing("JiraProvider was used before configure() was called")
        return self._config, self._client
