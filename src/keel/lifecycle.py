"""Project lifecycle phases — single source of truth.

The phase lifecycle is now customizable via `keel.lifecycles`. This module
provides backward-compatible wrappers around the default lifecycle.
"""

from __future__ import annotations


def _default_lifecycle():
    """Lazy accessor; the loader has its own caching by virtue of being deterministic."""
    from keel.lifecycles import load_lifecycle

    return load_lifecycle("default")


def _default_phases() -> list[str]:
    """Return the default lifecycle's states in linear `transitions` order.

    Walks `transitions` from `initial` until a state has no successor or the chain
    revisits a state. Used to produce the legacy `PHASES` list shape.
    """
    lc = _default_lifecycle()
    out: list[str] = []
    seen: set[str] = set()
    cur: str | None = lc.initial
    while cur is not None and cur not in seen:
        out.append(cur)
        seen.add(cur)
        nexts = lc.transitions.get(cur, [])
        cur = nexts[0] if nexts else None
    return out


# Backward-compatible top-level constants. Computed at import time; if a user
# tweaks the default lifecycle TOML, restart the process to pick up changes.
PHASES: list[str] = _default_phases()
DEFAULT_PHASE: str = _default_lifecycle().initial


def next_phase(current: str) -> str | None:
    """Return the next phase in the default lifecycle, or None at the end."""
    lc = _default_lifecycle()
    if current not in lc.states:
        return None
    nexts = lc.transitions.get(current, [])
    return nexts[0] if nexts else None


def is_valid_phase(name: str) -> bool:
    """True if `name` is a state in the default lifecycle."""
    return name in _default_lifecycle().states


# Milestone/task states are intentionally separate from the phase lifecycle FSM.
# Phases govern the project/deliverable; these govern work items within them.
MILESTONE_STATES: list[str] = ["planned", "active", "done", "cancelled"]
TASK_STATES: list[str] = MILESTONE_STATES  # same set; alias for clarity at call sites

DEFAULT_MILESTONE_STATE: str = MILESTONE_STATES[0]
DEFAULT_TASK_STATE: str = TASK_STATES[0]

_TERMINAL_STATES = frozenset({"done", "cancelled"})


def is_valid_milestone_state(name: str) -> bool:
    return name in MILESTONE_STATES


def is_valid_task_state(name: str) -> bool:
    return name in TASK_STATES


def is_terminal_milestone_state(name: str) -> bool:
    return name in _TERMINAL_STATES


def is_terminal_task_state(name: str) -> bool:
    return name in _TERMINAL_STATES
