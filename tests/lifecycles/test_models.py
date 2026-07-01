"""Tests for Lifecycle / LifecycleState Pydantic models."""

import pytest
from pydantic import ValidationError

from keel.lifecycles.models import Lifecycle, LifecycleState


def _minimal_lifecycle(**overrides):
    base = {
        "name": "test",
        "initial": "a",
        "terminal": ["c"],
        "states": {"a": {}, "b": {}, "c": {}},
        "transitions": {"a": ["b"], "b": ["c"]},
    }
    base.update(overrides)
    return Lifecycle.model_validate(base)


def test_lifecycle_state_defaults() -> None:
    s = LifecycleState()
    assert s.description == ""
    assert s.cancellable is True


def test_lifecycle_minimal_round_trip() -> None:
    lc = _minimal_lifecycle()
    assert lc.name == "test"
    assert lc.initial == "a"
    assert lc.terminal == ["c"]
    assert "a" in lc.states


def test_lifecycle_initial_must_be_in_states() -> None:
    with pytest.raises(ValidationError):
        _minimal_lifecycle(initial="ghost")


def test_lifecycle_terminal_must_be_in_states() -> None:
    with pytest.raises(ValidationError):
        _minimal_lifecycle(terminal=["ghost"])


def test_lifecycle_transitions_keys_must_be_in_states() -> None:
    with pytest.raises(ValidationError):
        _minimal_lifecycle(transitions={"ghost": ["c"]})


def test_lifecycle_transitions_values_must_be_in_states() -> None:
    with pytest.raises(ValidationError):
        _minimal_lifecycle(transitions={"a": ["ghost"]})


def test_lifecycle_successors_simple() -> None:
    lc = _minimal_lifecycle()
    assert lc.successors("a") == ["b"]


def test_lifecycle_successors_includes_implicit_cancelled() -> None:
    """If `cancelled` is in states, every cancellable state gets the implicit edge."""
    lc = Lifecycle.model_validate(
        {
            "name": "test",
            "initial": "a",
            "terminal": ["c", "cancelled"],
            "states": {"a": {}, "b": {}, "c": {}, "cancelled": {}},
            "transitions": {"a": ["b"], "b": ["c"]},
        }
    )
    succs = lc.successors("a")
    assert "b" in succs
    assert "cancelled" in succs


def test_lifecycle_successors_omits_cancelled_when_state_opted_out() -> None:
    lc = Lifecycle.model_validate(
        {
            "name": "test",
            "initial": "a",
            "terminal": ["c", "cancelled"],
            "states": {"a": {"cancellable": False}, "b": {}, "c": {}, "cancelled": {}},
            "transitions": {"a": ["b"], "b": ["c"]},
        }
    )
    succs = lc.successors("a")
    assert "cancelled" not in succs


def test_lifecycle_successors_no_cancelled_state_means_no_implicit_edge() -> None:
    lc = _minimal_lifecycle()  # no cancelled state declared
    succs = lc.successors("a")
    assert "cancelled" not in succs


def test_lifecycle_is_terminal() -> None:
    lc = _minimal_lifecycle()
    assert lc.is_terminal("c") is True
    assert lc.is_terminal("a") is False


def test_lifecycle_unknown_state_raises_on_successors() -> None:
    lc = _minimal_lifecycle()
    with pytest.raises(KeyError):
        lc.successors("ghost")


def test_lifecycle_rejects_uppercase_state_name() -> None:
    with pytest.raises(ValidationError, match="state name"):
        _minimal_lifecycle(states={"Active": {}, "b": {}, "c": {}})


def test_lifecycle_rejects_state_name_with_spaces() -> None:
    with pytest.raises(ValidationError, match="state name"):
        _minimal_lifecycle(states={"in review": {}, "b": {}, "c": {}})


def test_lifecycle_accepts_kebab_case_state_name() -> None:
    lc = Lifecycle.model_validate(
        {
            "name": "test",
            "initial": "in-review",
            "terminal": ["done"],
            "states": {"in-review": {}, "done": {}},
            "transitions": {"in-review": ["done"]},
        }
    )
    assert "in-review" in lc.states
