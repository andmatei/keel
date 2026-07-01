"""Pydantic models for `[extensions.ai]` in project.toml."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriggerWhen(BaseModel):
    """Optional condition filter on a trigger — matches event payload fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    to: str | None = None
    from_state: str | None = Field(None, alias="from")


class Trigger(BaseModel):
    """A single trigger mapping a keel event to an AI action."""

    model_config = ConfigDict(extra="forbid")

    event: str
    when: TriggerWhen | None = None
    action: str
    mode: str | None = None
    enabled: bool = True


class AISkills(BaseModel):
    """Skill routing — which skill handles each workflow phase."""

    model_config = ConfigDict(extra="forbid")

    scope: str = "writing-scopes"
    design: str = "writing-tech-designs"
    plan: str = "superpowers:writing-plans"


class AgentsMdConfig(BaseModel):
    """Configuration for AGENTS.md generation."""

    model_config = ConfigDict(extra="forbid")

    extra: str | None = None


class AIConfig(BaseModel):
    """Top-level schema for [extensions.ai] in project.toml."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    triggers: dict[str, Trigger] = Field(default_factory=dict)
    skills: AISkills = Field(default_factory=AISkills)
    agents_md: AgentsMdConfig = Field(default_factory=AgentsMdConfig)


DEFAULT_LIFECYCLE_TRIGGERS: dict[str, Trigger] = {
    "task_done_sync": Trigger(
        event="task.status.post",
        when=TriggerWhen(to="done"),
        action="design-sync",
        mode="lightweight",
    ),
    "task_done_review": Trigger(
        event="task.status.post",
        when=TriggerWhen(to="done"),
        action="code-review",
    ),
    "milestone_done_sync": Trigger(
        event="milestone.status.post",
        when=TriggerWhen(to="done"),
        action="design-sync",
        mode="thorough",
    ),
    "milestone_done_review": Trigger(
        event="milestone.status.post",
        when=TriggerWhen(to="done"),
        action="code-review",
    ),
}


def parse_ai_config(raw: dict[str, Any] | None) -> AIConfig:
    """Parse and validate an [extensions.ai] dict. Returns defaults if raw is None or empty."""
    if not raw:
        return AIConfig()
    return AIConfig.model_validate(raw)


def resolve_triggers(ai_config: AIConfig, lifecycle: str) -> dict[str, Trigger]:
    """Resolve effective triggers: lifecycle defaults merged with user config.

    User triggers override defaults by name. Setting ``enabled: false``
    on a default trigger name disables it.
    """
    if lifecycle == "default":
        merged = dict(DEFAULT_LIFECYCLE_TRIGGERS)
    else:
        merged = {}
    merged.update(ai_config.triggers)
    return {name: t for name, t in merged.items() if t.enabled}
