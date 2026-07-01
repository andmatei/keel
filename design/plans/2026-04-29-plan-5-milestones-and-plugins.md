# Plan 5: Milestones, tasks, and the ticketing plugin protocol

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the **milestones + tasks** feature to keel. Milestones group related implementation work. Tasks are atomic units with a directed acyclic dependency graph; each task lives on its own branch and can opt into a per-task worktree via the existing `keel code` group. Plus the **`TicketProvider` plugin protocol** in keel core: an abstraction with discovery via Python entry points, a mock provider for tests, and zero coupling to any specific ticketing system. Real ticketing integrations (Jira, GitHub, Linear, Notion) ship as separate, independently-maintained `keel-<provider>` packages — Plan 6+ territory.

**Architecture:**

```
keel-cli (this plan)
├── milestones.toml manifest               # NEW per-unit manifest
├── keel.lifecycle (extended)              # state-set helpers reused for milestones/tasks
├── keel.ticketing                         # NEW — protocol + registry + mock
│   ├── base.py                            # TicketProvider Protocol, Ticket dataclass
│   ├── registry.py                        # entry-point discovery
│   └── mock.py                            # in-memory provider for tests
└── commands/                              # NEW subpackages
    ├── milestone/                         # add, list, show, start, done, cancel, rm
    ├── task/                              # add, list, show, start, done, cancel, rm, graph

keel-jira (Plan 6, separate package)        # NOT in this plan
keel-github (Plan 7+, separate)              # NOT in this plan
```

**Tech Stack:** Same as Plans 1-4.5. New: `networkx` lightweight import for DAG cycle detection? No — write a small inline cycle check; `networkx` is overkill for this scale (typical project: <50 tasks).

---

## Pre-decided open questions

1. **Milestone + task statuses**: same four-state set as `phase` and the milestone-cancelled discussion (`planned`/`active`/`done`/`cancelled`). State machine: `planned → active → done` forward; `* → cancelled` from any state; backward transitions allowed with a confirm prompt (matches `phase`).

2. **Milestones at which level(s)**: project-level by default. A project milestone can optionally fan out to per-deliverable sub-milestones via a `fan_out: ["deliverable-name", ...]` field. Each named deliverable's `milestones.toml` declares a `parent` field linking back. Project milestone is `done` when every fan-out deliverable's matching milestone is `done`. *Not in M1 — implemented in M2's milestone commands.*

3. **Manifest location**: `<unit>/design/milestones.toml`. Separate from `project.toml`/`deliverable.toml` because the work-tracking concern is separate from the code-linkage concern (and the file gets long when there are many tasks).

4. **DAG validation**: `keel validate` learns a "tasks" check (off by default; enabled by `--check tasks` or always when a `milestones.toml` exists). Validates: every `task.milestone` references an existing milestone id; every `depends_on` entry references an existing task id; the dependency graph is acyclic; project milestones with `fan_out` reference existing deliverables.

5. **Worktree-per-task**: NOT a default. Each task has a `branch` field (auto-set when started). Worktrees are created on-demand via the existing `keel code add --branch <task-branch>`. A small sugar command `keel task worktree <task-id>` does the lookup-and-add.

6. **Plugin model**: pure separation. keel-cli ships the protocol and discovery; *no real provider* lives in core. A mock provider (in `keel.ticketing.mock`) covers test cases. Real providers (`keel-jira`, etc.) are separate packages.

7. **Plugin discovery**: Python entry points, group `keel.ticket_providers`. Activation: when `project.toml` has `[ticketing]` with `provider = "<name>"` and the named plugin is installed, that provider is loaded.

8. **`--push` semantics**: when ticketing is configured AND a provider plugin is installed, milestone/task create+done commands push to the ticketing system by default. `--no-push` skips for one invocation. With no ticketing config, the flag is accepted but has no effect.

9. **Status mapping** (the customisability layer from the brainstorm): provider's defaults map keel's neutral states (`planned`/`active`/`done`/`cancelled`) to the provider's native states. Per-project overrides via `[ticketing.status_map]` in `project.toml` — *not* implemented in Plan 5; deferred to Plan 5.5 polish or to first-plugin (Plan 6). The protocol accepts the override config dict if present.

10. **Customisable phase lifecycle DSL** (parking-lot): NOT in Plan 5. Stays parked. Plan 5 hardcodes the 4-state set for milestones/tasks; the DSL extension is its own future plan.

11. **`networkx` dependency**: not added. Inline cycle detection is ~10 lines of DFS-based code and avoids a dependency.

---

## File structure

After Plan 5 lands:

```
~/projects/keel/
└── src/keel/
    ├── lifecycle.py                          # MODIFY — add MILESTONE_STATES, TASK_STATES, transition validators
    ├── manifest.py                           # MODIFY — add MilestonesManifest schema (loaded separately)
    ├── ticketing/                            # NEW
    │   ├── __init__.py                       # re-exports
    │   ├── base.py                           # TicketProvider Protocol + Ticket dataclass
    │   ├── registry.py                       # entry-point loader
    │   └── mock.py                           # MockProvider for tests
    ├── api.py                                # MODIFY — re-export from keel.ticketing where stable
    └── commands/
        ├── milestone/                        # NEW
        │   ├── __init__.py
        │   ├── add.py
        │   ├── list.py
        │   ├── show.py
        │   ├── start.py
        │   ├── done.py
        │   ├── cancel.py
        │   └── rm.py
        └── task/                             # NEW
            ├── __init__.py
            ├── add.py
            ├── list.py
            ├── show.py
            ├── start.py
            ├── done.py
            ├── cancel.py
            ├── rm.py
            ├── graph.py
            └── worktree.py                  # sugar: keel task worktree <id> -> code add

tests/
├── test_lifecycle.py                         # MODIFY — tests for new state sets
├── test_manifest.py                          # MODIFY — milestones manifest tests
├── test_ticketing.py                         # NEW — protocol contract tests + MockProvider tests
└── commands/
    ├── milestone/                            # NEW (mirrors src/keel/commands/milestone/)
    └── task/                                 # NEW

design/decisions/
└── 2026-04-29-plan-5-plugin-model.md         # NEW — record the pure-plugin choice (no bundled providers)
```

---

## Pre-requisites

- Plan 4.5 is complete (`keel-plan-4.5` tag exists)
- 267 tests passing on `main`
- Ruff clean
- `keel.api`, `keel.testing`, `keel.lifecycle` modules exist (from 4.5)
- The empty `ticketing` Typer subapp is pre-registered in `app.py` (from 4.5)

---

## Milestone 1: Schema layer — milestones.toml and Pydantic models

### Task 1.1: Decision file recording the pure-plugin model

**Files:**
- Create: `design/decisions/2026-04-29-plan-5-plugin-model.md`

- [ ] **Step 1: Write the decision**

```markdown
---
date: 2026-04-29
title: Pure-plugin ticketing model — no bundled providers in keel core
status: accepted
---

# Pure-plugin ticketing model — no bundled providers in keel core

## Question

When designing the ticketing integration, should keel core bundle one provider
(e.g. Jira) for "out-of-box" ergonomics, or should ALL providers be plugins —
including the ones the maintainer uses?

## Options explored

### Option A: Bundle Jira in core; treat others as plugins

- Pros: zero-friction Jira usage (just `pip install keel-cli`).
- Cons: keel core gains a Jira-specific dependency tree; users who don't use
  Jira pay (download size, bug surface). Two ticketing code paths from day
  one (the bundled one and the plugin one). Plugin protocol risks getting
  shaped around Jira's quirks rather than designed for arbitrary providers.

### Option B: Bundle Jira as a plugin shipped in the same wheel

- Pros: the protocol is the only protocol; bundled provider validates the
  plugin pattern end-to-end.
- Cons: still ships Jira-specific code to non-Jira users.

### Option C: Pure separation — keel core ships only the protocol + a mock

- Pros: keel core stays minimal and dependency-free for ticketing. Real
  providers (`keel-jira`, `keel-github`, `keel-linear`, `keel-notion`) are
  separate packages, each developed and maintained on its own cadence.
  Plugin protocol is never tempted to specialise for one provider. Users
  install only what they use.
- Cons: a Jira user must explicitly `pip install keel-jira`.

## Conclusion

**Option C.** keel-cli ships only the `TicketProvider` protocol, the
plugin-discovery mechanism (Python entry points), and a `MockProvider` for
tests. No real provider — including Jira — lives in core. `keel-jira` is a
separate, developed-and-maintained package; same for any future provider.

## Consequences

- The plugin protocol must be designed for arbitrary providers from the
  start; no Jira-specific shortcuts.
- Plan 5 (this plan) implements core. Plan 6 implements the first real
  plugin (`keel-jira`), as its own package.
- Users who want ticketing run `pip install keel-cli keel-jira` (or similar).
  This becomes the documented install command for that workflow.
- Test coverage for the protocol uses the `MockProvider`; integration with
  real services is the responsibility of each plugin package's own test
  suite.
```

- [ ] **Step 2: Commit**

```bash
git add keel/design/decisions/2026-04-29-plan-5-plugin-model.md
git commit -m "docs(keel): record decision — pure-plugin ticketing, no bundled providers"
```

---

### Task 1.2: Extend `keel.lifecycle` with milestone/task state sets

**Files:**
- Modify: `src/keel/lifecycle.py`
- Modify: `tests/test_lifecycle.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_lifecycle.py`:

```python
from keel.lifecycle import (
    MILESTONE_STATES, TASK_STATES,
    DEFAULT_MILESTONE_STATE, DEFAULT_TASK_STATE,
    is_valid_milestone_state, is_valid_task_state,
    is_terminal_milestone_state, is_terminal_task_state,
)


def test_milestone_states() -> None:
    assert MILESTONE_STATES == ["planned", "active", "done", "cancelled"]
    assert DEFAULT_MILESTONE_STATE == "planned"


def test_task_states() -> None:
    """Task states currently mirror milestone states."""
    assert TASK_STATES == MILESTONE_STATES
    assert DEFAULT_TASK_STATE == "planned"


def test_is_valid_milestone_state() -> None:
    for s in MILESTONE_STATES:
        assert is_valid_milestone_state(s)
    assert not is_valid_milestone_state("bogus")
    assert not is_valid_milestone_state("")


def test_is_terminal_state() -> None:
    assert is_terminal_milestone_state("done")
    assert is_terminal_milestone_state("cancelled")
    assert not is_terminal_milestone_state("planned")
    assert not is_terminal_milestone_state("active")
    assert is_terminal_task_state("done")
    assert is_terminal_task_state("cancelled")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd ~/projects/keel && uv run --extra dev pytest tests/test_lifecycle.py -v`
Expected: 4 NEW fail.

- [ ] **Step 3: Extend `src/keel/lifecycle.py`**

Append:

```python
# Milestone and task state sets — currently identical, but kept as separate
# constants so they can diverge later if needed (e.g. tasks gaining a `blocked`
# state, milestones losing one).
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
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Add the new symbols to `keel.api`**

In `src/keel/api.py`, add to imports + `__all__`:
- `MILESTONE_STATES`, `TASK_STATES`, `DEFAULT_MILESTONE_STATE`, `DEFAULT_TASK_STATE`
- `is_valid_milestone_state`, `is_valid_task_state`, `is_terminal_milestone_state`, `is_terminal_task_state`

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/lifecycle.py keel/src/keel/api.py keel/tests/test_lifecycle.py
git commit -m "feat(keel): add MILESTONE_STATES/TASK_STATES to lifecycle module"
```

---

### Task 1.3: `Milestone` and `Task` Pydantic models

**Files:**
- Modify: `src/keel/manifest.py`
- Modify: `tests/test_manifest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_manifest.py`:

```python
from keel.manifest import (
    Milestone, Task, MilestonesManifest,
    load_milestones_manifest, save_milestones_manifest,
)


def test_milestone_minimal() -> None:
    m = Milestone(id="m1", title="Foundation")
    assert m.id == "m1"
    assert m.status == "planned"
    assert m.fan_out == []
    assert m.jira_id is None


def test_milestone_with_fan_out() -> None:
    m = Milestone(id="m1", title="Ship X", fan_out=["foo", "bar"])
    assert m.fan_out == ["foo", "bar"]


def test_milestone_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Milestone(id="m1", title="t", status="bogus")


def test_milestone_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        Milestone(id="", title="t")


def test_task_minimal() -> None:
    t = Task(id="t1", milestone="m1", title="Set up")
    assert t.status == "planned"
    assert t.depends_on == []
    assert t.branch is None


def test_task_with_dependencies() -> None:
    t = Task(id="t2", milestone="m1", title="x", depends_on=["t1"])
    assert t.depends_on == ["t1"]


def test_milestones_manifest_minimal() -> None:
    m = MilestonesManifest()
    assert m.milestones == []
    assert m.tasks == []


def test_milestones_manifest_round_trip(tmp_path) -> None:
    path = tmp_path / "milestones.toml"
    original = MilestonesManifest(
        milestones=[
            Milestone(id="m1", title="Foundation", status="active"),
            Milestone(id="m2", title="Deliverable", fan_out=["foo"]),
        ],
        tasks=[
            Task(id="t1", milestone="m1", title="Set up", status="done", branch="me/keel-m1-t1"),
            Task(id="t2", milestone="m1", title="Add models", depends_on=["t1"], branch="me/keel-m1-t2"),
        ],
    )
    save_milestones_manifest(path, original)
    loaded = load_milestones_manifest(path)
    assert loaded == original


def test_milestones_manifest_load_missing_file_returns_empty(tmp_path) -> None:
    """If milestones.toml doesn't exist, load returns an empty manifest (not an error)."""
    path = tmp_path / "milestones.toml"
    m = load_milestones_manifest(path)
    assert m.milestones == []
    assert m.tasks == []
```

- [ ] **Step 2: Run, expect 9 FAIL**

- [ ] **Step 3: Implement the models**

Append to `src/keel/manifest.py`:

```python
from keel.lifecycle import (
    MILESTONE_STATES, TASK_STATES,
    DEFAULT_MILESTONE_STATE, DEFAULT_TASK_STATE,
)


class Milestone(BaseModel):
    """A grouping of related implementation work, scoped to the `implementing` phase."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, description="Stable identifier within the unit (e.g. 'm1', 'foundation').")
    title: str = Field(min_length=1)
    description: str = ""
    status: str = Field(default=DEFAULT_MILESTONE_STATE)
    fan_out: list[str] = Field(default_factory=list, description="Deliverable names this milestone fans out to.")
    parent: str | None = Field(default=None, description="If this is a sub-milestone, the parent milestone's id at the project level.")
    jira_id: str | None = None

    @field_validator("status")
    @classmethod
    def _status_in_set(cls, v: str) -> str:
        if v not in MILESTONE_STATES:
            raise ValueError(f"status must be one of {MILESTONE_STATES}")
        return v


class Task(BaseModel):
    """An atomic unit of work under a milestone."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    milestone: str = Field(min_length=1, description="The owning milestone's id.")
    title: str = Field(min_length=1)
    description: str = ""
    status: str = Field(default=DEFAULT_TASK_STATE)
    depends_on: list[str] = Field(default_factory=list, description="Other task ids that must be done before this can start.")
    branch: str | None = Field(default=None, description="Git branch for this task. Auto-set when started.")
    jira_id: str | None = None

    @field_validator("status")
    @classmethod
    def _status_in_set(cls, v: str) -> str:
        if v not in TASK_STATES:
            raise ValueError(f"status must be one of {TASK_STATES}")
        return v


class MilestonesManifest(BaseModel):
    """Schema for `<unit>/design/milestones.toml`."""

    model_config = ConfigDict(extra="forbid")

    milestones: list[Milestone] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)


def load_milestones_manifest(path: Path) -> MilestonesManifest:
    """Read and validate `milestones.toml`. Returns an empty manifest if the file doesn't exist."""
    if not path.is_file():
        return MilestonesManifest()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return MilestonesManifest.model_validate(raw)


def save_milestones_manifest(path: Path, manifest: MilestonesManifest) -> None:
    doc = tomlkit.document()
    if manifest.milestones:
        ms_array = tomlkit.aot()
        for m in manifest.milestones:
            ms_array.append(tomlkit.item(_dict_no_none(m.model_dump())))
        doc["milestones"] = ms_array
    if manifest.tasks:
        ts_array = tomlkit.aot()
        for t in manifest.tasks:
            ts_array.append(tomlkit.item(_dict_no_none(t.model_dump())))
        doc["tasks"] = ts_array
    path.write_text(tomlkit.dumps(doc))
```

- [ ] **Step 4: Run, expect all PASS**

- [ ] **Step 5: Add to keel.api**

In `src/keel/api.py`: add `Milestone`, `Task`, `MilestonesManifest`, `load_milestones_manifest`, `save_milestones_manifest` to imports + `__all__`.

- [ ] **Step 6: Add a `milestones_manifest_path` workspace helper**

In `src/keel/workspace.py`:

```python
def milestones_manifest_path(project: str, deliverable: str | None = None) -> Path:
    """Path to the milestones.toml file for the given scope."""
    return design_dir(project, deliverable) / "milestones.toml"
```

Add a `Scope.milestones_manifest_path` property:

```python
    @property
    def milestones_manifest_path(self) -> Path:
        return self.design_dir / "milestones.toml"
```

Tests for both in `tests/test_workspace.py` (parallel to the existing `manifest_path` tests).

- [ ] **Step 7: Commit**

```bash
git add keel/src/keel/manifest.py keel/src/keel/workspace.py keel/src/keel/api.py keel/tests/test_manifest.py keel/tests/test_workspace.py
git commit -m "feat(keel): add Milestone/Task/MilestonesManifest models + workspace helpers"
```

---

### Task 1.4: DAG validation helpers

**Files:**
- Create: `src/keel/milestones.py` (graph helpers — separate from `manifest.py` to keep schema and graph logic apart)
- Create: `tests/test_milestones_graph.py`

- [ ] **Step 1: Write tests**

Create `tests/test_milestones_graph.py`:

```python
"""Tests for DAG helpers in keel.milestones."""
import pytest
from keel.manifest import MilestonesManifest, Milestone, Task
from keel.milestones import (
    validate_dag,
    GraphError,
    ready_tasks,
    blocked_tasks,
    topological_sort,
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
```

- [ ] **Step 2: Run, expect collection error**

- [ ] **Step 3: Implement `src/keel/milestones.py`**

```python
"""Graph helpers for milestone + task DAG validation and queries."""
from __future__ import annotations
from keel.manifest import MilestonesManifest, Milestone, Task
from keel.lifecycle import is_terminal_task_state


class GraphError(ValueError):
    """Raised when the milestone/task graph is malformed."""


def validate_dag(m: MilestonesManifest) -> None:
    """Validate that the milestone/task graph is well-formed.

    Checks:
    - Every task.milestone references an existing milestone id
    - Every depends_on entry references an existing task id
    - The dependency graph is acyclic
    """
    milestone_ids = {ms.id for ms in m.milestones}
    task_ids = {t.id for t in m.tasks}

    for t in m.tasks:
        if t.milestone not in milestone_ids:
            raise GraphError(
                f"task {t.id!r} references unknown milestone {t.milestone!r}"
            )
        for dep in t.depends_on:
            if dep not in task_ids:
                raise GraphError(
                    f"task {t.id!r} depends_on unknown task {dep!r}"
                )

    # Check for cycles via DFS-based color marking.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {tid: WHITE for tid in task_ids}
    deps: dict[str, list[str]] = {t.id: t.depends_on for t in m.tasks}

    def dfs(node: str, path: list[str]) -> None:
        if color[node] == GRAY:
            cycle_start = path.index(node)
            cycle = " -> ".join(path[cycle_start:] + [node])
            raise GraphError(f"cycle detected: {cycle}")
        if color[node] == BLACK:
            return
        color[node] = GRAY
        path.append(node)
        for dep in deps[node]:
            dfs(dep, path)
        path.pop()
        color[node] = BLACK

    for tid in task_ids:
        if color[tid] == WHITE:
            dfs(tid, [])


def ready_tasks(m: MilestonesManifest) -> list[Task]:
    """Tasks with status=planned and all dependencies in a terminal (done/cancelled) state."""
    by_id = {t.id: t for t in m.tasks}
    out: list[Task] = []
    for t in m.tasks:
        if t.status != "planned":
            continue
        if all(is_terminal_task_state(by_id[d].status) for d in t.depends_on if d in by_id):
            out.append(t)
    return out


def blocked_tasks(m: MilestonesManifest) -> list[Task]:
    """Tasks with status=planned but at least one dependency in a non-terminal state."""
    by_id = {t.id: t for t in m.tasks}
    out: list[Task] = []
    for t in m.tasks:
        if t.status != "planned":
            continue
        if any(not is_terminal_task_state(by_id[d].status) for d in t.depends_on if d in by_id):
            out.append(t)
    return out


def topological_sort(m: MilestonesManifest) -> list[Task]:
    """Return tasks in dependency order (deps first). Raises GraphError on cycle."""
    validate_dag(m)
    by_id = {t.id: t for t in m.tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in m.tasks}
    for t in m.tasks:
        for dep in t.depends_on:
            if dep in in_degree:
                in_degree[t.id] += 1

    # Kahn's algorithm
    queue: list[str] = [tid for tid, d in in_degree.items() if d == 0]
    out: list[Task] = []
    while queue:
        # Stable order: take the lexically-first ready task each step
        queue.sort()
        tid = queue.pop(0)
        out.append(by_id[tid])
        for t in m.tasks:
            if tid in t.depends_on:
                in_degree[t.id] -= 1
                if in_degree[t.id] == 0:
                    queue.append(t.id)
    return out
```

- [ ] **Step 4: Run, expect all PASS**

- [ ] **Step 5: Add to keel.api**

In `src/keel/api.py`, add `validate_dag`, `GraphError`, `ready_tasks`, `blocked_tasks`, `topological_sort` from `keel.milestones`.

- [ ] **Step 6: Commit**

```bash
git add keel/src/keel/milestones.py keel/src/keel/api.py keel/tests/test_milestones_graph.py
git commit -m "feat(keel): add DAG validation and ready/blocked/topo helpers"
```

---

## Milestone 2: `keel milestone` command group

### Task 2.1: Scaffold `commands/milestone/` subpackage

- Create `src/keel/commands/milestone/__init__.py` with the Typer subapp.
- Create empty `tests/commands/milestone/__init__.py`.
- Register in `src/keel/app.py`: `from keel.commands.milestone import app as milestone_app; app.add_typer(milestone_app, name="milestone")`.

Standard scaffold pattern from previous plans. Smoke check: `keel milestone --help` shows the empty group help. Run full suite. Commit:

```bash
git commit -m "feat(keel): scaffold milestone command group"
```

---

### Task 2.2: `keel milestone add <id> --title "..."`

**Files:**
- Create: `src/keel/commands/milestone/add.py`
- Create: `tests/commands/milestone/test_add.py`
- Modify: `src/keel/commands/milestone/__init__.py` (register)

Behavior:
- Resolve scope via `workspace.resolve_cli_scope(project, deliverable, out=out)`.
- Load existing `milestones.toml` (returns empty manifest if missing).
- Validate the new id doesn't collide with existing milestones.
- Build the new `Milestone` (defaults: status=`planned`).
- Save back via `save_milestones_manifest`.
- `--no-push` flag accepted but no-op until M4 wires ticketing.

Standard TDD: 4-5 tests covering happy path, duplicate id rejection, dry-run, JSON output. Commit:

```bash
git commit -m "feat(keel): implement 'milestone add'"
```

---

### Task 2.3: `keel milestone list`

Same shape as `keel deliverable list` from Plan 2 — load manifest, render Rich table or JSON. Filters: `--status`, `--milestone <id>` (when listing tasks via the task command, not relevant here). Standard 3-4 tests. Commit:

```bash
git commit -m "feat(keel): implement 'milestone list'"
```

---

### Task 2.4: `keel milestone show <id>`

Renders a milestone's metadata, status, fan-out, and contained tasks (count + breakdown by status). 3 tests. Commit:

```bash
git commit -m "feat(keel): implement 'milestone show'"
```

---

### Task 2.5: `keel milestone start <id>` / `done <id>` / `cancel <id>`

Status transitions. Each is a small command:

- `start`: status `planned → active`. Reject if status isn't `planned`.
- `done`: status `active → done`. Reject if status isn't `active`. If milestone has `fan_out`, validate every fan-out deliverable's matching milestone is `done` first; otherwise warn and require `--force`.
- `cancel`: status `* → cancelled`. From any state. Confirm prompt.

Backwards transitions (e.g., `done → active` if you realize work isn't done) handled via a `--reopen` flag on `start` that allows `done → active`. Three tests per command (happy path, wrong-state rejection, --force/--reopen path). Commit each separately:

```bash
git commit -m "feat(keel): implement 'milestone start' / 'done' / 'cancel'"
```

(All three in one commit is fine since they share the helper.)

---

### Task 2.6: `keel milestone rm <id>`

Only allowed when milestone status is `cancelled` (or with `--force`). Removes the milestone entry. If tasks reference the milestone, fail with a clear error pointing to those tasks. Confirm prompt unless `-y`. Commit:

```bash
git commit -m "feat(keel): implement 'milestone rm'"
```

---

## Milestone 3: `keel task` command group

### Task 3.1: Scaffold `commands/task/` subpackage

Same shape as M2.1. Commit.

### Task 3.2: `keel task add <id> --milestone <m-id> --title "..."`

- Validates milestone exists.
- Validates `--depends-on a,b` references existing tasks.
- After save, runs `validate_dag` on the manifest; rejects if it fails (cycle introduction protection).
- 5 tests (happy, unknown milestone, unknown dep, cycle introduction, --depends-on multiple).

Commit:

```bash
git commit -m "feat(keel): implement 'task add' with DAG validation on save"
```

### Task 3.3: `keel task list`

- Filters: `--milestone M`, `--status S`, `--ready` (only ready tasks via `ready_tasks(m)`), `--blocked` (only blocked).
- Default output: table grouped by milestone.
- `--json` flat list with `state` field plus a derived `ready: bool` field for convenience.

Commit:

```bash
git commit -m "feat(keel): implement 'task list' with --ready/--blocked filters"
```

### Task 3.4: `keel task show <id>` / `start <id>` / `done <id>` / `cancel <id>`

`show`: renders metadata + dependency tree (which deps are done, which aren't).

`start`: status `planned → active`. Computes a default branch name (`<user-slug>/<project>-<milestone-id>-<task-id>`) and stores it on the Task. If the user passes `--branch NAME`, uses that instead. If the worktree's current state allows, checks out the branch (creating it from the worktree's default base branch). If not currently in a worktree, just records the branch — user can use `keel task worktree <id>` later.

`done`: status `active → done`. Stores no automated git action (the user has already committed/merged on their own).

`cancel`: status `* → cancelled`. Confirm.

5-6 tests across the four. Commit each (or bundle into 2 commits: `show` separately, transitions together).

### Task 3.5: `keel task graph [--milestone M]`

Render the task DAG as ASCII (an indented tree showing dependency chains). Optional `--dot` flag emits Graphviz DOT format for piping to `dot -Tpng`. JSON option emits the topological sort order plus per-task ready/blocked metadata.

Implementation: ASCII renderer is small (~50 lines); DOT is one line per node + edge.

Commit:

```bash
git commit -m "feat(keel): implement 'task graph' (ASCII + --dot + --json)"
```

### Task 3.6: `keel task rm <id>`

Same shape as `milestone rm`. Refuses if other tasks depend on this one (orphan-protection); `--force` skips the check.

### Task 3.7: `keel task worktree <id>` (sugar)

Looks up the task's branch from the manifest, finds the appropriate `[[repos]]` entry on the project's manifest (or whichever repo the worktree should belong to — probably the only one for a single-repo project; ambiguous for multi-repo, in which case require `--repo`), then invokes the same logic as `keel code add --repo <repo> --worktree <name> --branch <branch>`.

Effectively a 5-line command that delegates to `code add`'s underlying helper. Commit.

---

## Milestone 4: Ticketing plugin protocol

### Task 4.1: `src/keel/ticketing/base.py` — Protocol + Ticket dataclass

```python
"""Ticketing plugin protocol.

Plugin authors implement TicketProvider; keel core uses it via the registry.
keel core ships zero real providers — only this protocol and a MockProvider
in keel.ticketing.mock for tests.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Ticket:
    """Provider-agnostic ticket reference."""
    id: str
    url: str
    title: str | None = None
    status: str | None = None  # provider's native status, not keel's neutral state


@runtime_checkable
class TicketProvider(Protocol):
    """Protocol for ticketing plugins.

    A plugin package registers a TicketProvider via the `keel.ticket_providers`
    entry-point group. keel core uses this protocol; it never imports the
    plugin's internals.

    The neutral status names are: planned, active, done, cancelled.
    Each provider is responsible for mapping these to its native states
    (and back).
    """

    name: str  # e.g. "jira", "github", "linear"

    def configure(self, config: dict) -> None:
        """Validate and accept the [extensions.ticketing.<name>] config dict."""
        ...

    def create_milestone(self, parent_id: str, title: str, description: str) -> Ticket:
        """Create a ticket representing a milestone (typically a Story under an Epic).

        `parent_id` is the project-level Epic id (or equivalent), from
        [ticketing] parent_id in the project manifest.
        """
        ...

    def create_task(self, parent_milestone_id: str, title: str, description: str) -> Ticket:
        """Create a ticket representing a task (typically a Subtask under the milestone's Story)."""
        ...

    def transition(self, ticket_id: str, target_state: str) -> None:
        """Move a ticket to one of: planned, active, done, cancelled."""
        ...

    def fetch(self, ticket_id: str) -> Ticket:
        """Re-read a ticket's state. Used by `keel * refresh` commands."""
        ...

    def link_url(self, ticket_id: str) -> str:
        """Return a clickable URL to view the ticket in the provider's UI."""
        ...
```

Plus `tests/test_ticketing.py` with smoke tests (Protocol attributes exist, runtime_checkable, etc.).

Add `Ticket` and `TicketProvider` to `keel.api`.

Commit:

```bash
git commit -m "feat(keel): add TicketProvider protocol + Ticket dataclass"
```

### Task 4.2: `src/keel/ticketing/registry.py` — entry-point loader

```python
"""Plugin discovery via Python entry points.

Plugin packages declare in their pyproject.toml:

    [project.entry-points."keel.ticket_providers"]
    jira = "keel_jira.provider:JiraProvider"

keel.ticketing.registry.load_provider(name) finds and instantiates the matching
provider. Returns None if no provider is registered with that name (do not raise
— callers handle the "not installed" case).
"""
from __future__ import annotations
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from keel.ticketing.base import TicketProvider


def load_provider(name: str) -> "TicketProvider | None":
    """Find and instantiate the named TicketProvider, or return None if not found."""
    for ep in entry_points(group="keel.ticket_providers"):
        if ep.name != name:
            continue
        try:
            cls = ep.load()
        except Exception:
            return None
        try:
            instance = cls()
        except Exception:
            return None
        return instance
    return None


def list_providers() -> list[str]:
    """Names of all installed ticketing providers."""
    return sorted({ep.name for ep in entry_points(group="keel.ticket_providers")})
```

Tests use entry-point fixtures (`monkeypatch.setattr` on `importlib.metadata.entry_points`). 4 tests.

Add `load_provider`, `list_providers` to `keel.api`.

Commit:

```bash
git commit -m "feat(keel): add ticketing plugin registry"
```

### Task 4.3: `src/keel/ticketing/mock.py` — MockProvider for tests

In-memory provider that implements the full protocol; useful for keel's own tests AND for plugin authors to compare against. Records all calls so tests can assert on them.

```python
"""Mock ticketing provider for tests.

Records calls in a list so tests can assert on them. Used both by keel core
tests and as a reference for plugin authors.

Example use in keel.testing:

    from keel.ticketing.mock import MockProvider
    provider = MockProvider()
    provider.create_milestone("EPIC-1", "Foundation", "")
    assert provider.calls[-1] == ("create_milestone", "EPIC-1", "Foundation", "")
"""
# ... ~80 lines of straightforward implementation
```

Plus tests verifying it satisfies the Protocol (via `isinstance` since the protocol is `@runtime_checkable`).

Add `MockProvider` to `keel.testing` (NOT to `keel.api` — it's a testing utility, not a stable public surface).

Commit:

```bash
git commit -m "feat(keel): add MockProvider in keel.ticketing.mock for tests"
```

### Task 4.4: Wire `[ticketing]` config into project.toml + activation

Add a small reader in `src/keel/ticketing/__init__.py`:

```python
def get_provider_for_project(manifest: ProjectManifest) -> "TicketProvider | None":
    """Read [extensions.ticketing] from the project manifest, instantiate the provider, configure it.
    Returns None if no ticketing config or the provider plugin isn't installed.
    """
    cfg = manifest.extensions.get("ticketing")
    if not isinstance(cfg, dict):
        return None
    name = cfg.get("provider")
    if not name:
        return None
    provider = load_provider(name)
    if provider is None:
        return None
    provider.configure(cfg.get(name, {}))  # provider-specific subsection
    return provider
```

Tests that exercise the lookup with MockProvider registered as a fake entry point.

Commit:

```bash
git commit -m "feat(keel): wire [extensions.ticketing] config to provider activation"
```

### Task 4.5: `--push` / `--no-push` on milestone/task add and done

Wire the activation:
- `milestone add --no-push` (or absence of ticketing config) → local-only.
- With ticketing configured + provider installed + no `--no-push` → call `provider.create_milestone(...)`, store `ticket.id` on the Milestone's `jira_id` field (it's named for Jira but used for any provider id).
- `milestone done` → `provider.transition(ticket_id, "done")`.
- Same shape for task add/done.

Tests use MockProvider via a fixture in `keel.testing`.

Commit:

```bash
git commit -m "feat(keel): --push flag on milestone/task add+done routes through provider"
```

---

## Milestone 5: Final smoke + tag

- [ ] Full suite passes (~330+ tests; Plan 5 adds ~60).
- [ ] Ruff clean.
- [ ] Smoke check end-to-end:
  ```bash
  PROJECTS_DIR=/tmp/keel-p5-smoke keel new alpha -d "test" --no-worktree -y
  PROJECTS_DIR=/tmp/keel-p5-smoke keel milestone add m1 --title "Foundation" --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task add t1 --milestone m1 --title "Set up" --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task add t2 --milestone m1 --title "Deps" --depends-on t1 --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task list --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task graph --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel milestone start m1 --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task start t1 --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task done t1 --project alpha
  PROJECTS_DIR=/tmp/keel-p5-smoke keel task list --ready --project alpha   # should now show t2
  find /tmp/keel-p5-smoke -delete 2>/dev/null
  ```
- [ ] Tag: `git tag keel-plan-5`.

---

## Self-review

| Brainstorm item | Implementing tasks |
|---|---|
| Milestones at project level (with optional fan_out to deliverables) | Task 1.3 (schema with fan_out field), 2.5 (done validates fan-out completion) |
| Tasks with DAG dependencies | Tasks 1.3 (Task model), 1.4 (validate_dag), 3.2 (cycle prevention on add) |
| Each task on its own branch | Task 3.4 (start sets branch) |
| On-demand worktrees (not per-task) | Task 3.7 (sugar invoking existing code add) |
| 4-state lifecycle (planned/active/done/cancelled) | Tasks 1.2 (lifecycle constants), 2.5/3.4 (transitions) |
| Pluggable ticketing (no bundled providers in core) | Tasks 4.1 (Protocol), 4.2 (registry), 4.3 (mock), 4.4 (config wiring), 4.5 (push semantics) |
| Status mapping customisability (Layer 2) | Deferred — provider's `configure()` accepts the dict but Plan 5 doesn't add a per-project `status_map` override yet |
| Customisable phase lifecycle DSL | Still parked (out of scope for Plan 5) |

**No placeholders** — every step has actual code or a clear pattern to apply.

---

## What this plan does NOT cover

- **Plan 6: `keel-jira` plugin** — separate package, separate plan, depends on Plan 5's protocol.
- **Plan 7+: GH Issues / Linear / Notion plugins** — same pattern, separate plans.
- **Status-map customisation** — the `[ticketing.status_map]` override section in `project.toml` is a Plan 5.5 polish item.
- **Customisable phase lifecycle DSL** — parking-lot from earlier brainstorm.
- **Two-way Jira sync / auto-refresh** — manual `keel * refresh` only; live polling is out of scope.
