"""Central dispatcher — fans events out to all subscribers in documented order."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from keel.hooks.loader import load_plugin_listeners
from keel.hooks.registry import iter_matching_subscribers
from keel.hooks.scripts import discover_hook_scripts, run_user_script
from keel.hooks.types import HookEvent

if TYPE_CHECKING:
    from keel.output import Output


_plugins_loaded = False


def _ensure_plugins_loaded() -> None:
    """Load plugin event-listener entry points lazily, once per process."""
    global _plugins_loaded
    if _plugins_loaded:
        return
    load_plugin_listeners()
    _plugins_loaded = True


def dispatch(
    event: HookEvent,
    *,
    out: Output,
    workspace_dir: Path,
    project_dir: Path | None,
) -> None:
    """Fire the event to all subscribers in documented order.

    Order: in-tree (registration order) → workspace user-script → project user-script.
    (Plugin subscribers register into the in-tree registry on first dispatch
    via load_plugin_listeners.)

    Pre-events: any subscriber exception propagates and aborts the caller.
    Post-events: exceptions are caught and emitted via out.warn(); the loop
    continues.
    """
    _ensure_plugins_loaded()

    is_pre = event.phase == "pre"

    # 1. In-tree subscribers (includes plugin-registered subscribers post-load).
    for subscriber in iter_matching_subscribers(event.full_name):
        try:
            subscriber(event, out=out)
        except Exception as e:
            if is_pre:
                raise
            out.warn(f"post-hook subscriber failed: {e}")

    # 2. User scripts (workspace then project).
    pairs = discover_hook_scripts(
        event_full_name=event.full_name,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
    )
    for script, layer in pairs:
        try:
            run_user_script(script, event, layer=layer)
        except Exception as e:
            if is_pre:
                raise
            out.warn(f"post-hook script '{script}' failed: {e}")
