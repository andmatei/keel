"""Tests for DAG helpers in keel.milestones."""

import pytest

from keel.manifest import Milestone, MilestonesManifest, Task
from keel.milestones import (
    GraphError,
    blocked_tasks,
    ready_tasks,
    topological_sort,
    validate_dag,
)


def _manifest(milestones, tasks):
    return MilestonesManifest(milestones=milestones, tasks=tasks)


def test_validate_dag_clean() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a"),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"]),
        ],
    )
    validate_dag(m)  # no exception


def test_validate_dag_unknown_milestone_ref() -> None:
    m = _manifest([], [Task(id="t1", milestone="ghost", title="x")])
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "ghost" in str(exc.value)


def test_validate_dag_unknown_dep_ref() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [Task(id="t1", milestone="m1", title="x", depends_on=["nonexistent"])],
    )
    with pytest.raises(GraphError):
        validate_dag(m)


def test_validate_dag_cycle() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a", depends_on=["t2"]),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"]),
        ],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "cycle" in str(exc.value).lower()


def test_ready_tasks() -> None:
    """Tasks with status=planned and all deps done are ready."""
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a", status="done"),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"], status="planned"),
            Task(id="t3", milestone="m1", title="c", depends_on=["t1"], status="planned"),
            Task(id="t4", milestone="m1", title="d", depends_on=["t2"], status="planned"),
        ],
    )
    ready = ready_tasks(m)
    assert {t.id for t in ready} == {"t2", "t3"}


def test_blocked_tasks() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a", status="planned"),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"], status="planned"),
        ],
    )
    blocked = blocked_tasks(m)
    assert {t.id for t in blocked} == {"t2"}


def test_topological_sort() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a"),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"]),
            Task(id="t3", milestone="m1", title="c", depends_on=["t1"]),
            Task(id="t4", milestone="m1", title="d", depends_on=["t2", "t3"]),
        ],
    )
    order = [t.id for t in topological_sort(m)]
    # t1 comes before t2 and t3; t2 and t3 come before t4
    assert order.index("t1") < order.index("t2")
    assert order.index("t1") < order.index("t3")
    assert order.index("t2") < order.index("t4")
    assert order.index("t3") < order.index("t4")


def test_validate_dag_self_loop() -> None:
    """A task that depends on itself is a cycle."""
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [Task(id="t1", milestone="m1", title="a", depends_on=["t1"])],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "cycle" in str(exc.value).lower()


def test_validate_dag_three_cycle() -> None:
    """A 3-node cycle is detected."""
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a", depends_on=["t3"]),
            Task(id="t2", milestone="m1", title="b", depends_on=["t1"]),
            Task(id="t3", milestone="m1", title="c", depends_on=["t2"]),
        ],
    )
    with pytest.raises(GraphError):
        validate_dag(m)


def test_validate_dag_empty() -> None:
    """An empty manifest is trivially acyclic."""
    m = MilestonesManifest()
    validate_dag(m)  # no exception


def test_topological_sort_empty() -> None:
    m = MilestonesManifest()
    assert topological_sort(m) == []


def test_validate_dag_duplicate_milestone_id() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x"), Milestone(id="m1", title="y")],
        [],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "duplicate" in str(exc.value).lower()


def test_validate_dag_duplicate_task_id() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="t1", milestone="m1", title="a"),
            Task(id="t1", milestone="m1", title="b"),
        ],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "duplicate" in str(exc.value).lower()


def test_validate_dag_unknown_parent_ref() -> None:
    m = _manifest(
        [Milestone(id="m1", title="x", parent="ghost")],
        [],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "ghost" in str(exc.value)


def test_validate_dag_self_referential_parent() -> None:
    """A milestone that is its own parent is rejected."""
    m = _manifest(
        [Milestone(id="m1", title="x", parent="m1")],
        [],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "own parent" in str(exc.value).lower()


def test_validate_dag_transitive_parent_cycle() -> None:
    """A cycle in the milestone parent chain (m1→m2→m1) is detected."""
    m = _manifest(
        [
            Milestone(id="m1", title="x", parent="m2"),
            Milestone(id="m2", title="y", parent="m1"),
        ],
        [],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "cycle" in str(exc.value).lower()


def test_validate_dag_valid_parent_accepted() -> None:
    """A milestone with a valid parent reference passes validation."""
    m = _manifest(
        [Milestone(id="m1", title="x"), Milestone(id="m2", title="y", parent="m1")],
        [],
    )
    validate_dag(m)  # no exception


def test_ready_tasks_dangling_dep_blocks() -> None:
    """A task with a depends_on referencing a non-existent ID is blocked, not ready."""
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [Task(id="t1", milestone="m1", title="a", depends_on=["deleted-task"])],
    )
    ready = ready_tasks(m)
    assert len(ready) == 0
    blocked = blocked_tasks(m)
    assert len(blocked) == 1


def test_topological_sort_disconnected_components() -> None:
    """Topological sort handles two unconnected components correctly."""
    m = _manifest(
        [Milestone(id="m1", title="x")],
        [
            Task(id="a1", milestone="m1", title="a"),
            Task(id="a2", milestone="m1", title="a", depends_on=["a1"]),
            Task(id="b1", milestone="m1", title="b"),
            Task(id="b2", milestone="m1", title="b", depends_on=["b1"]),
        ],
    )
    order = [t.id for t in topological_sort(m)]
    assert order.index("a1") < order.index("a2")
    assert order.index("b1") < order.index("b2")


def test_validate_dag_cross_namespace_id_collision() -> None:
    """A milestone and task sharing the same ID is rejected."""
    m = _manifest(
        [Milestone(id="shared", title="x")],
        [Task(id="shared", milestone="shared", title="a")],
    )
    with pytest.raises(GraphError) as exc:
        validate_dag(m)
    assert "shared" in str(exc.value)
    assert "both milestone and task" in str(exc.value).lower()
