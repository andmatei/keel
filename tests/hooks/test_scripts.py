"""Tests for the user-script runner."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_run_script_passes_positional_args(tmp_path: Path, make_executable_script) -> None:
    """Script receives positional_args as argv."""
    from keel.hooks import HookEvent
    from keel.hooks.scripts import run_user_script

    out_file = tmp_path / "args.txt"
    script = tmp_path / "project.phase.post"
    make_executable_script(
        script,
        f'#!/usr/bin/env bash\necho "$1 $2" > {out_file}\n',
    )

    event = HookEvent(
        entity="project",
        action="phase",
        phase="post",
        project="foo",
        deliverable=None,
        payload={"from": "scoping", "to": "designing"},
        positional_args=("scoping", "designing"),
    )
    run_user_script(script, event, layer="workspace")
    assert out_file.read_text().strip() == "scoping designing"


def test_run_script_sets_env_vars(tmp_path: Path, make_executable_script) -> None:
    """KEEL_EVENT, KEEL_ENTITY, KEEL_ACTION, KEEL_PHASE, KEEL_PROJECT,
    KEEL_HOOK_LAYER, and per-event extras are set."""
    from keel.hooks import HookEvent
    from keel.hooks.scripts import run_user_script

    out_file = tmp_path / "env.txt"
    script = tmp_path / "project.phase.post"
    make_executable_script(
        script,
        f"#!/usr/bin/env bash\nenv | grep ^KEEL_ | sort > {out_file}\n",
    )

    event = HookEvent(
        entity="project",
        action="phase",
        phase="post",
        project="foo",
        deliverable="bar",
        payload={"from": "scoping", "to": "designing"},
        positional_args=("scoping", "designing"),
    )
    run_user_script(script, event, layer="project")
    env_dump = out_file.read_text()
    assert "KEEL_EVENT=project.phase.post" in env_dump
    assert "KEEL_ENTITY=project" in env_dump
    assert "KEEL_ACTION=phase" in env_dump
    assert "KEEL_PHASE=post" in env_dump
    assert "KEEL_PROJECT=foo" in env_dump
    assert "KEEL_DELIVERABLE=bar" in env_dump
    assert "KEEL_HOOK_LAYER=project" in env_dump
    assert "KEEL_PHASE_FROM=scoping" in env_dump
    assert "KEEL_PHASE_TO=designing" in env_dump


def test_run_script_passes_payload_on_stdin(tmp_path: Path, make_executable_script) -> None:
    """The full event payload arrives on stdin as JSON."""
    from keel.hooks import HookEvent
    from keel.hooks.scripts import run_user_script

    out_file = tmp_path / "stdin.txt"
    script = tmp_path / "decision.create.post"
    make_executable_script(
        script,
        f"#!/usr/bin/env bash\ncat > {out_file}\n",
    )

    event = HookEvent(
        entity="decision",
        action="create",
        phase="post",
        project="foo",
        deliverable=None,
        payload={"slug": "use-postgres", "title": "Use Postgres", "supersedes": None},
        positional_args=("use-postgres",),
    )
    run_user_script(script, event, layer="workspace")

    import json

    parsed = json.loads(out_file.read_text())
    assert parsed["payload"]["slug"] == "use-postgres"
    assert parsed["entity"] == "decision"
    assert parsed["action"] == "create"
    assert parsed["phase"] == "post"


def test_run_script_non_zero_exit_raises(tmp_path: Path, make_executable_script) -> None:
    """A script exiting non-zero raises HookAborted with the stderr message."""
    from keel.hooks import HookAborted, HookEvent
    from keel.hooks.scripts import run_user_script

    script = tmp_path / "project.phase.pre"
    make_executable_script(
        script,
        '#!/usr/bin/env bash\necho "nope, blocked" >&2\nexit 1\n',
    )

    event = HookEvent(
        entity="project",
        action="phase",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={"from": "scoping", "to": "designing"},
        positional_args=("scoping", "designing"),
    )
    with pytest.raises(HookAborted) as exc:
        run_user_script(script, event, layer="workspace")
    assert "nope, blocked" in str(exc.value)


def test_run_script_skipped_if_not_executable(tmp_path: Path) -> None:
    """Non-executable scripts are skipped silently (matches git)."""
    from keel.hooks import HookEvent
    from keel.hooks.scripts import run_user_script

    script = tmp_path / "project.phase.post"
    script.write_text("#!/usr/bin/env bash\nfail\n")
    # NOT chmod'ed executable
    assert not os.access(script, os.X_OK)

    event = HookEvent(
        entity="project",
        action="phase",
        phase="post",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=(),
    )
    # Should not raise — silently skipped
    run_user_script(script, event, layer="workspace")


def test_discover_hook_scripts_finds_workspace_and_project(tmp_path: Path, make_executable_script) -> None:
    """discover_hook_scripts returns workspace hook first, then project hook."""
    from keel.hooks.scripts import discover_hook_scripts

    workspace_hooks = tmp_path / "ws" / ".keel" / "hooks"
    workspace_hooks.mkdir(parents=True)
    project_hooks = tmp_path / "proj" / ".keel" / "hooks"
    project_hooks.mkdir(parents=True)

    ws_script = workspace_hooks / "project.phase.post"
    make_executable_script(ws_script, "#!/bin/sh\n")
    proj_script = project_hooks / "project.phase.post"
    make_executable_script(proj_script, "#!/bin/sh\n")

    discovered = discover_hook_scripts(
        event_full_name="project.phase.post",
        workspace_dir=tmp_path / "ws",
        project_dir=tmp_path / "proj",
    )
    # Returns (script_path, layer) pairs in order: workspace first
    assert discovered == [
        (ws_script, "workspace"),
        (proj_script, "project"),
    ]


def test_run_script_timeout_raises_hook_aborted(tmp_path: Path, make_executable_script) -> None:
    """A script exceeding the timeout raises HookAborted."""
    import subprocess
    from unittest.mock import patch

    from keel.hooks import HookAborted, HookEvent
    from keel.hooks.scripts import run_user_script

    script = tmp_path / "project.phase.pre"
    make_executable_script(script, "#!/usr/bin/env bash\nsleep 999\n")

    event = HookEvent(
        entity="project",
        action="phase",
        phase="pre",
        project="foo",
        deliverable=None,
        payload={},
        positional_args=(),
    )
    with (
        patch(
            "keel.hooks.scripts.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=str(script), timeout=30),
        ),
        pytest.raises(HookAborted, match="timed out after 30s"),
    ):
        run_user_script(script, event, layer="workspace")


def test_discover_hook_scripts_omits_missing(tmp_path: Path, make_executable_script) -> None:
    """If a layer doesn't have the script, it's just absent from the result."""
    from keel.hooks.scripts import discover_hook_scripts

    project_hooks = tmp_path / "proj" / ".keel" / "hooks"
    project_hooks.mkdir(parents=True)
    proj_script = project_hooks / "project.phase.post"
    make_executable_script(proj_script, "#!/bin/sh\n")

    # No workspace dir
    discovered = discover_hook_scripts(
        event_full_name="project.phase.post",
        workspace_dir=tmp_path / "nonexistent-ws",
        project_dir=tmp_path / "proj",
    )
    assert discovered == [(proj_script, "project")]
