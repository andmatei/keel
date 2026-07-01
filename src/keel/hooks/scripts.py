"""User-script runner — fork/exec git-style hooks under .keel/hooks/."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Literal

from keel.hooks.types import HookAborted, HookEvent

Layer = Literal["workspace", "project"]

_HOOK_TIMEOUT_SECS = 30


def _event_to_env(event: HookEvent, layer: Layer) -> dict[str, str]:
    """Compute the env-var subset added on top of the parent env."""
    env: dict[str, str] = {
        "KEEL_EVENT": event.full_name,
        "KEEL_ENTITY": event.entity,
        "KEEL_ACTION": event.action,
        "KEEL_PHASE": event.phase,
        "KEEL_HOOK_LAYER": layer,
    }
    if event.project is not None:
        env["KEEL_PROJECT"] = event.project
    if event.deliverable is not None:
        env["KEEL_DELIVERABLE"] = event.deliverable

    # Per-event extras: KEEL_<ACTION_UPPER>_<FIELD_UPPER> = str(value)
    # e.g. event.action="phase", payload={"from": "scoping"} -> KEEL_PHASE_FROM=scoping
    action_upper = event.action.upper()
    for key, value in event.payload.items():
        if value is None:
            continue
        field_upper = key.replace("-", "_").upper()
        env_val = str(value).lower() if isinstance(value, bool) else str(value)
        env[f"KEEL_{action_upper}_{field_upper}"] = env_val
    return env


def discover_hook_scripts(
    *,
    event_full_name: str,
    workspace_dir: Path,
    project_dir: Path | None,
) -> list[tuple[Path, Layer]]:
    """Return (script_path, layer) pairs to run, workspace first.

    Caller passes the actual workspace dir (e.g. PROJECTS_DIR) and project
    dir (or None for events not scoped to a project).
    """
    pairs: list[tuple[Path, Layer]] = []
    workspace_script = workspace_dir / ".keel" / "hooks" / event_full_name
    if workspace_script.is_file() and os.access(workspace_script, os.X_OK):
        pairs.append((workspace_script, "workspace"))
    if project_dir is not None:
        project_script = project_dir / ".keel" / "hooks" / event_full_name
        if project_script.is_file() and os.access(project_script, os.X_OK):
            pairs.append((project_script, "project"))
    return pairs


def run_user_script(script: Path, event: HookEvent, *, layer: Layer) -> None:
    """Execute a single user-script hook.

    - argv: [str(script), *event.positional_args]
    - env: parent env + KEEL_* vars
    - stdin: JSON of {name, phase, project, deliverable, payload}
    - non-zero exit (and not skipped-for-non-exec): HookAborted

    A non-executable script is skipped silently (matches git).
    """
    if not os.access(script, os.X_OK):
        return

    env = {**os.environ, **_event_to_env(event, layer)}
    stdin_data = json.dumps(
        {
            "entity": event.entity,
            "action": event.action,
            "phase": event.phase,
            "project": event.project,
            "deliverable": event.deliverable,
            "payload": event.payload,
        }
    )

    try:
        result = subprocess.run(
            [str(script), *event.positional_args],
            env=env,
            input=stdin_data,
            capture_output=True,
            text=True,
            check=False,
            timeout=_HOOK_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        raise HookAborted(
            f"hook '{script.name}' (layer={layer}) timed out after {_HOOK_TIMEOUT_SECS}s"
        )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        msg = f"hook '{script.name}' (layer={layer}) exited {result.returncode}" + (
            f": {stderr}" if stderr else ""
        )
        raise HookAborted(msg)
