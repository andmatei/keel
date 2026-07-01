"""Tests for match_triggers.py — custom action routing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

MATCH_TRIGGERS = str(
    Path(__file__).resolve().parents[2] / "plugins" / "keel-ai" / "hooks" / "match_triggers.py"
)


def _run_match_triggers(config: dict, event: str, to_status: str) -> str | None:
    result = subprocess.run(
        [sys.executable, MATCH_TRIGGERS, event, to_status],
        input=json.dumps(config),
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


class TestKnownActions:
    def test_design_sync_produces_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                    "mode": "lightweight",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/design-sync --lightweight" in ctx

    def test_code_review_produces_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "code-review",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "code-reviewer" in ctx


class TestCustomActions:
    def test_unknown_action_produces_generic_instruction(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "my-custom-skill",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/my-custom-skill" in ctx

    def test_unknown_action_with_mode(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "milestone.status.post",
                    "when": {"to": "done"},
                    "action": "deploy-check",
                    "mode": "full",
                },
            },
        }
        output = _run_match_triggers(config, "milestone.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/deploy-check --full" in ctx

    def test_multiple_triggers_all_listed(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                    "mode": "lightweight",
                },
                "t2": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "my-lint",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "done")
        assert output is not None
        parsed = json.loads(output)
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "/design-sync" in ctx
        assert "/my-lint" in ctx


class TestNoMatch:
    def test_no_matching_triggers_exits_silently(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                },
            },
        }
        output = _run_match_triggers(config, "milestone.status.post", "done")
        assert output is None

    def test_wrong_status_no_match(self) -> None:
        config = {
            "resolved_triggers": {
                "t1": {
                    "event": "task.status.post",
                    "when": {"to": "done"},
                    "action": "design-sync",
                },
            },
        }
        output = _run_match_triggers(config, "task.status.post", "active")
        assert output is None
