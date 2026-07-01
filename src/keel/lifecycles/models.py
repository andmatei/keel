"""Pydantic schema for a phase lifecycle.

A `Lifecycle` defines a finite-state machine: a set of states (phases),
allowed transitions between them, an initial state for new projects, and one
or more terminal states.

Cancellation is implicit: if a `cancelled` state is declared, every state
where `cancellable=True` (the default) gets an implicit `<state> -> cancelled`
edge added on top of any explicit transitions.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_STATE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class LifecycleState(BaseModel):
    """One node in the lifecycle FSM."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = ""
    cancellable: bool = True


class Lifecycle(BaseModel):
    """A named phase lifecycle (a finite state machine over phase names)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    description: str = ""
    initial: str = Field(min_length=1)
    terminal: list[str] = Field(min_length=1)
    states: dict[str, LifecycleState] = Field(min_length=1)
    transitions: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("states", mode="before")
    @classmethod
    def _validate_state_names(cls, v: dict) -> dict:
        for name in v:
            if not _STATE_NAME_RE.match(name):
                raise ValueError(
                    f"state name {name!r} must be lowercase alphanumeric + hyphens, "
                    f"start with a letter (e.g. 'scoping', 'in-review')"
                )
        return v

    @model_validator(mode="after")
    def _check_referenced_names(self) -> Lifecycle:
        names = set(self.states)
        if self.initial not in names:
            raise ValueError(f"initial state '{self.initial}' is not in [states]")
        for t in self.terminal:
            if t not in names:
                raise ValueError(f"terminal state '{t}' is not in [states]")
        for src, dests in self.transitions.items():
            if src not in names:
                raise ValueError(f"transitions key '{src}' is not in [states]")
            for d in dests:
                if d not in names:
                    raise ValueError(
                        f"transitions['{src}'] contains '{d}' which is not in [states]"
                    )
        return self

    def successors(self, current: str) -> list[str]:
        """Return allowed next states from `current`, including implicit cancelled.

        Raises KeyError if `current` is not a declared state.
        """
        if current not in self.states:
            raise KeyError(current)
        explicit = list(self.transitions.get(current, []))
        if (
            "cancelled" in self.states
            and self.states[current].cancellable
            and current != "cancelled"
            and "cancelled" not in explicit
        ):
            explicit.append("cancelled")
        return explicit

    def is_terminal(self, state: str) -> bool:
        """True if `state` is in the lifecycle's terminal set."""
        return state in self.terminal
