"""Tests for keel.ai.config — AIConfig model validation."""

from __future__ import annotations

import pytest

from keel.ai.config import (
    AIConfig,
    AISkills,
    AgentsMdConfig,
    Trigger,
    TriggerWhen,
    parse_ai_config,
    resolve_triggers,
)


# -- TriggerWhen --


def test_trigger_when_empty() -> None:
    tw = TriggerWhen()
    assert tw.to is None
    assert tw.from_state is None


def test_trigger_when_to_only() -> None:
    tw = TriggerWhen(to="done")
    assert tw.to == "done"
    assert tw.from_state is None


def test_trigger_when_from_alias() -> None:
    """TOML key is 'from'; Python attr is 'from_state'."""
    tw = TriggerWhen.model_validate({"from": "active"})
    assert tw.from_state == "active"


def test_trigger_when_roundtrip_alias() -> None:
    tw = TriggerWhen(to="done", from_state="active")
    dumped = tw.model_dump(by_alias=True)
    assert dumped == {"to": "done", "from": "active"}


# -- Trigger --


def test_trigger_minimal() -> None:
    t = Trigger(event="task.status.post", action="design-sync")
    assert t.event == "task.status.post"
    assert t.action == "design-sync"
    assert t.when is None
    assert t.mode is None
    assert t.enabled is True


def test_trigger_full() -> None:
    t = Trigger(
        event="milestone.status.post",
        when=TriggerWhen(to="done"),
        action="design-sync",
        mode="thorough",
        enabled=True,
    )
    assert t.when.to == "done"
    assert t.mode == "thorough"


def test_trigger_disabled() -> None:
    t = Trigger(event="project.phase.post", action="x", enabled=False)
    assert t.enabled is False


def test_trigger_missing_event_fails() -> None:
    with pytest.raises(Exception):
        Trigger(action="x")  # type: ignore[call-arg]


def test_trigger_missing_action_fails() -> None:
    with pytest.raises(Exception):
        Trigger(event="x")  # type: ignore[call-arg]


# -- AISkills --


def test_ai_skills_defaults() -> None:
    s = AISkills()
    assert s.scope == "writing-scopes"
    assert s.design == "writing-tech-designs"
    assert s.plan == "superpowers:writing-plans"


def test_ai_skills_override() -> None:
    s = AISkills(scope="my-custom-scope")
    assert s.scope == "my-custom-scope"
    assert s.design == "writing-tech-designs"


# -- AgentsMdConfig --


def test_agents_md_config_default() -> None:
    c = AgentsMdConfig()
    assert c.extra is None


def test_agents_md_config_with_extra() -> None:
    c = AgentsMdConfig(extra=".keel/agents-md-extra.md")
    assert c.extra == ".keel/agents-md-extra.md"


# -- AIConfig --


def test_ai_config_defaults() -> None:
    cfg = AIConfig()
    assert cfg.enabled is True
    assert cfg.triggers == {}
    assert isinstance(cfg.skills, AISkills)
    assert isinstance(cfg.agents_md, AgentsMdConfig)


def test_ai_config_disabled() -> None:
    cfg = AIConfig(enabled=False)
    assert cfg.enabled is False


def test_ai_config_from_toml_dict() -> None:
    """Validate a dict that mirrors what TOML parsing would produce."""
    raw = {
        "enabled": True,
        "triggers": {
            "task_done": {
                "event": "task.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "lightweight",
            },
            "milestone_done": {
                "event": "milestone.status.post",
                "when": {"to": "done"},
                "action": "design-sync",
                "mode": "thorough",
            },
        },
        "skills": {"scope": "my-scope-skill"},
        "agents_md": {"extra": ".keel/extra.md"},
    }
    cfg = AIConfig.model_validate(raw)
    assert len(cfg.triggers) == 2
    assert cfg.triggers["task_done"].mode == "lightweight"
    assert cfg.triggers["milestone_done"].when.to == "done"
    assert cfg.skills.scope == "my-scope-skill"
    assert cfg.skills.design == "writing-tech-designs"
    assert cfg.agents_md.extra == ".keel/extra.md"


def test_ai_config_empty_dict() -> None:
    """Empty [extensions.ai] table should produce valid defaults."""
    cfg = AIConfig.model_validate({})
    assert cfg.enabled is True
    assert cfg.triggers == {}


def test_ai_config_unknown_field_rejected() -> None:
    with pytest.raises(Exception):
        AIConfig.model_validate({"bogus": True})


def test_ai_config_roundtrip_by_alias() -> None:
    raw = {
        "triggers": {
            "t": {
                "event": "task.status.post",
                "when": {"from": "active", "to": "done"},
                "action": "design-sync",
            }
        }
    }
    cfg = AIConfig.model_validate(raw)
    dumped = cfg.model_dump(by_alias=True)
    assert dumped["triggers"]["t"]["when"]["from"] == "active"


# -- parse_ai_config --


def test_parse_ai_config_helper() -> None:
    cfg = parse_ai_config({"enabled": False})
    assert cfg.enabled is False


def test_parse_ai_config_empty() -> None:
    cfg = parse_ai_config({})
    assert cfg.enabled is True


def test_parse_ai_config_none() -> None:
    cfg = parse_ai_config(None)
    assert cfg.enabled is True
    assert cfg.triggers == {}


# -- resolve_triggers --


def test_resolve_default_lifecycle_provides_defaults() -> None:
    """Default lifecycle populates triggers even with no user config."""
    cfg = AIConfig()
    resolved = resolve_triggers(cfg, "default")
    assert "task_done_sync" in resolved
    assert "task_done_review" in resolved
    assert "milestone_done_sync" in resolved
    assert "milestone_done_review" in resolved
    assert resolved["task_done_sync"].action == "design-sync"
    assert resolved["task_done_sync"].mode == "lightweight"
    assert resolved["milestone_done_sync"].mode == "thorough"
    assert resolved["task_done_review"].action == "code-review"


def test_resolve_non_default_lifecycle_no_defaults() -> None:
    """Non-default lifecycle gets no default triggers."""
    cfg = AIConfig()
    resolved = resolve_triggers(cfg, "custom-lifecycle")
    assert resolved == {}


def test_resolve_user_override_replaces_default() -> None:
    """User trigger with same name as default replaces it."""
    cfg = AIConfig(
        triggers={
            "task_done_sync": Trigger(
                event="task.status.post",
                when=TriggerWhen(to="done"),
                action="my-custom-sync",
                mode="full",
            )
        }
    )
    resolved = resolve_triggers(cfg, "default")
    assert resolved["task_done_sync"].action == "my-custom-sync"
    assert resolved["task_done_sync"].mode == "full"
    assert "task_done_review" in resolved
    assert "milestone_done_sync" in resolved


def test_resolve_user_disables_default() -> None:
    """Setting enabled=false on a default trigger name removes it."""
    cfg = AIConfig(
        triggers={
            "task_done_review": Trigger(
                event="task.status.post",
                when=TriggerWhen(to="done"),
                action="code-review",
                enabled=False,
            )
        }
    )
    resolved = resolve_triggers(cfg, "default")
    assert "task_done_review" not in resolved
    assert "task_done_sync" in resolved


def test_resolve_user_adds_custom_trigger() -> None:
    """User-defined triggers are added alongside defaults."""
    cfg = AIConfig(
        triggers={
            "notify_slack": Trigger(
                event="task.status.post",
                when=TriggerWhen(to="done"),
                action="notify-team",
                mode="slack",
            )
        }
    )
    resolved = resolve_triggers(cfg, "default")
    assert "notify_slack" in resolved
    assert resolved["notify_slack"].action == "notify-team"
    assert "task_done_sync" in resolved


def test_resolve_non_default_lifecycle_with_user_triggers() -> None:
    """Non-default lifecycle still picks up user-configured triggers."""
    cfg = AIConfig(
        triggers={
            "my_trigger": Trigger(
                event="task.status.post",
                action="custom-action",
            )
        }
    )
    resolved = resolve_triggers(cfg, "waterfall")
    assert len(resolved) == 1
    assert "my_trigger" in resolved
