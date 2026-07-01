---
date: 2026-05-14
title: "Hooks v1: Dotted event namespace + milestone/task lifecycle events"
status: draft
prerequisite-for: keel-ai plugin
---

# Hooks v1: Dotted event namespace + milestone/task lifecycle events

## Summary

Evolve the hooks framework from flat kebab-case event names (`pre-new`,
`post-phase`) to a dotted namespace (`project.create.pre`,
`milestone.status.post`). Add hookability to all milestone and task
mutation commands. Add glob pattern subscriptions so plugins can
subscribe to `milestone.*` or `*.status.post`. Clean break — no backward
compatibility shim.

This is a prerequisite for keel-ai, which subscribes to lifecycle events
to trigger AI-assisted design updates.

## Motivation

The v0 hooks framework (Plan 9) proved the architecture: decorator-based
opt-in, central dispatcher, three subscriber tiers. But it left two gaps:

1. **No milestone/task events.** 9 commands hookable, 19+ mutation
   commands not. Task completion, milestone transitions, and task moves
   fire nothing. keel-ai (and any automation plugin) needs these.

2. **Flat naming doesn't scale.** `pre-deliverable-add` reads fine for 9
   events; at 19+ it becomes hard to group, filter, or configure. Dotted
   names (`deliverable.create.pre`) give natural hierarchy for glob
   patterns and config keys.

3. **No pattern subscriptions.** Each subscriber must register for exact
   event names. A plugin that wants "react to all post-events" must
   enumerate every event string and update when new events are added.

## Event naming convention

### Structure

```
<entity>.<action>.<phase>
```

- **entity**: `project`, `milestone`, `task`, `deliverable`, `decision`, `tag`
- **action**: `create`, `rm`, `status`, `phase`, `move`, `rename`, `archive`, `restore`, `add`
- **phase**: `pre`, `post`

### Full event catalog

**Project events (existing, renamed):**

| Command | Event |
|---|---|
| `keel new` | `project.create.{pre,post}` |
| `keel phase` | `project.phase.{pre,post}` |
| `keel archive` | `project.archive.{pre,post}` |
| `keel restore` | `project.restore.{pre,post}` |
| `keel rename` | `project.rename.{pre,post}` |

**Deliverable events (existing + new):**

| Command | Event |
|---|---|
| `keel deliverable add` | `deliverable.create.{pre,post}` |
| `keel deliverable rm` | `deliverable.rm.{pre,post}` |
| `keel deliverable rename` | `deliverable.rename.{pre,post}` |

**Decision events (existing, renamed):**

| Command | Event |
|---|---|
| `keel decision new` | `decision.create.{pre,post}` |

**Tag events (existing, renamed):**

| Command | Event |
|---|---|
| `keel tag add` | `tag.add.{pre,post}` |
| `keel tag rm` | `tag.rm.{pre,post}` |

**Milestone events (all new):**

| Command | Event |
|---|---|
| `keel milestone add` | `milestone.create.{pre,post}` |
| `keel milestone rm` | `milestone.rm.{pre,post}` |
| `keel milestone start` | `milestone.status.{pre,post}` |
| `keel milestone done` | `milestone.status.{pre,post}` |
| `keel milestone cancel` | `milestone.status.{pre,post}` |

**Task events (all new):**

| Command | Event |
|---|---|
| `keel task add` | `task.create.{pre,post}` |
| `keel task rm` | `task.rm.{pre,post}` |
| `keel task start` | `task.status.{pre,post}` |
| `keel task done` | `task.status.{pre,post}` |
| `keel task cancel` | `task.status.{pre,post}` |
| `keel task move` | `task.move.{pre,post}` |

**Total: 19 hookable commands, 38 event names (19 × pre + post).**

### Status events are lifecycle-agnostic

Status events (`milestone.status.*`, `task.status.*`) do NOT encode the
target state in the event name. The state machine may be customized per
project's lifecycle definition — hardcoding state names in event strings
would break when users define custom lifecycles.

Instead, status events carry `from` and `to` in the payload:

```python
# milestone.status.post payload for "keel milestone start m1":
{
    "id": "m1",
    "from": "planned",
    "to": "active",
    "command": "start",   # the CLI verb that triggered the transition
    "forced": False,      # whether --force or --reopen was used
}
```

Subscribers filter on payload fields:

```python
@subscribes_to("milestone.status.post")
def on_milestone_done(event: HookEvent, *, out: Output) -> None:
    if event.payload["to"] != "done":
        return
    # react to milestone completion
```

For user scripts, `KEEL_STATUS_FROM` and `KEEL_STATUS_TO` env vars carry
the same information.

This design supports future customizable milestone/task lifecycles
without any hooks framework changes.

## HookEvent model

The `HookEvent` dataclass gains structured fields:

```python
@dataclass(frozen=True)
class HookEvent:
    entity: str                      # "project", "milestone", "task", etc.
    action: str                      # "create", "status", "rm", etc.
    phase: Literal["pre", "post"]
    project: str | None
    deliverable: str | None
    payload: dict[str, Any]
    positional_args: tuple[str, ...]

    @property
    def full_name(self) -> str:
        return f"{self.entity}.{self.action}.{self.phase}"
```

The old `name` field is replaced by `entity` + `action`. The `full_name`
property produces the dotted string used for dispatch and script lookup.

### Env vars for user scripts

```
KEEL_EVENT=milestone.status.post    # full dotted name
KEEL_ENTITY=milestone
KEEL_ACTION=status
KEEL_PHASE=post
KEEL_PROJECT=foo
KEEL_DELIVERABLE=                   # empty if not scoped
KEEL_HOOK_LAYER=workspace           # or "project"

# Action-specific (status events):
KEEL_STATUS_FROM=planned
KEEL_STATUS_TO=active
KEEL_STATUS_COMMAND=start
KEEL_STATUS_FORCED=false

# Action-specific (create events):
KEEL_CREATE_ID=m1
KEEL_CREATE_TITLE=Foundation
```

Convention: `KEEL_<ACTION_UPPER>_<FIELD_UPPER>` for action-specific
payload fields. This replaces the v0 convention of
`KEEL_<EVENT_UPPER>_<FIELD_UPPER>` which used the old compound event
name.

## Pattern subscriptions

### Supported patterns

Glob matching via `fnmatch.fnmatch` (Python stdlib):

| Pattern | Matches |
|---|---|
| `milestone.status.post` | Exact match |
| `milestone.*.post` | All milestone post-events |
| `*.status.post` | All status changes (milestone + task) |
| `milestone.*` | All milestone events (pre + post, all actions) |
| `*.*.post` | All post-events |
| `*` | Everything |

### Registration

```python
@subscribes_to("milestone.status.post")   # exact
@subscribes_to("*.status.post")           # glob
def on_any_status_change(event: HookEvent, *, out: Output) -> None:
    ...
```

### User scripts

User scripts use exact event names only — the filename IS the event
name:

```
.keel/hooks/milestone.status.post    # fires on milestone status post
.keel/hooks/project.create.pre       # fires on project create pre
```

Dotted filenames work on all platforms. No glob filenames — users who
want broad matching write a plugin.

### Dispatch ordering

Within each tier (in-tree → plugin → user-script), exact matches fire
before glob matches. This ensures specific handlers run first.

## Dispatcher changes

The dispatch flow is unchanged (in-tree → plugin → user-scripts; pre
aborts on error, post warns). The registry becomes pattern-aware:

```python
_REGISTRY: dict[str, list[Subscriber]]
# Keys may be exact names ("milestone.status.post") or glob patterns ("*.status.*")
```

On each `dispatch(event)`:
1. Collect all matching subscribers by testing each registered pattern
   against `event.full_name` via `fnmatch`
2. Sort: exact matches first, then glob matches (within each tier)
3. Execute in tier order: in-tree → plugin → user-script

Since subscriber count is small (tens, not thousands), linear scan over
patterns is fine.

## Command-side API changes

### @hookable decorator

The decorator string changes to dotted format:

```python
# Before (v0):
@hookable("new")

# After (v1):
@hookable("project.create")
```

The decorator records the `entity.action` base name (without phase).
The `hook_event` context manager constructs the full `HookEvent` with
the phase.

### hook_event context manager

```python
with hook_event(
    "milestone.status",              # entity.action
    project="foo",
    payload={"id": "m1", "from": "planned", "to": "active",
             "command": "start", "forced": False},
    positional_args=("m1",),
    out=out,
    no_verify=no_verify,
) as ev:
    # milestone.status.pre fires on entry
    task.status = "active"
    ev.add_post_payload({"committed": True})
# milestone.status.post fires on clean exit
```

Internally, `hook_event` splits `"milestone.status"` into
`entity="milestone"`, `action="status"` and constructs two `HookEvent`
instances (pre and post).

## Built-in listener migration

The 5 existing phase-transition listeners in
`src/keel/hooks/builtin_listeners.py` update their `@subscribes_to`
strings:

| Old | New |
|---|---|
| `@subscribes_to("pre-phase")` | `@subscribes_to("project.phase.pre")` |
| `@subscribes_to("post-phase")` | `@subscribes_to("project.phase.post")` |

No logic changes — just the event name strings.

## Backward compatibility

**None.** Clean break. keel is pre-1.0 (`0.0.x`) with a single user.

- Old kebab-case event names stop working immediately
- User scripts at `.keel/hooks/pre-new` must be renamed to
  `.keel/hooks/project.create.pre`
- Plugin `@subscribes_to("pre-new")` must update to
  `@subscribes_to("project.create.pre")`
- No deprecation warnings, no shim, no bridge

## Payloads by event

### Project events

| Event | Pre payload | Post additions |
|---|---|---|
| `project.create` | `{description, lifecycle, tags}` | `{path}` |
| `project.phase` | `{from, to}` | — |
| `project.archive` | `{}` | `{archived_path}` |
| `project.restore` | `{}` | `{path}` |
| `project.rename` | `{old_name, new_name}` | — |

### Deliverable events

| Event | Pre payload | Post additions |
|---|---|---|
| `deliverable.create` | `{description}` | `{path}` |
| `deliverable.rm` | `{name}` | — |
| `deliverable.rename` | `{old_name, new_name}` | — |

### Decision events

| Event | Pre payload | Post additions |
|---|---|---|
| `decision.create` | `{slug, title, supersedes}` | `{path}` |

### Tag events

| Event | Pre payload | Post additions |
|---|---|---|
| `tag.add` | `{tag}` | — |
| `tag.rm` | `{tag}` | — |

### Milestone events

| Event | Pre payload | Post additions |
|---|---|---|
| `milestone.create` | `{id, title, parent, project, deliverable}` | — |
| `milestone.rm` | `{id}` | — |
| `milestone.status` | `{id, from, to, command, forced}` | — |

### Task events

| Event | Pre payload | Post additions |
|---|---|---|
| `task.create` | `{id, title, milestone, project, deliverable}` | — |
| `task.rm` | `{id}` | — |
| `task.status` | `{id, from, to, command, forced}` | — |
| `task.move` | `{id, from_milestone, to_milestone}` | — |

## Testing strategy

| Area | Tests |
|---|---|
| Event name migration | Verify all 9 existing hookable commands fire dotted names |
| New hookable commands | One integration test per new event (10 new hookable commands) |
| Pattern matching | Unit tests: exact match, single-wildcard, multi-wildcard, no-match |
| Pattern ordering | Exact subscribers fire before glob subscribers within each tier |
| Status payload | Verify `from`/`to`/`command`/`forced` fields for each transition type |
| Env var format | User script receives `KEEL_ENTITY`, `KEEL_ACTION`, `KEEL_STATUS_FROM`, etc. |
| Built-in listener migration | Phase preflights still fire on `project.phase.pre` |
| `keel hooks list` | Shows dotted event names, pattern subscribers |

## Out of scope

- **Customizable milestone/task lifecycles.** The hooks design supports
  any state names via payload fields, but the actual state machine
  remains hardcoded in this plan. Custom lifecycles are a separate spec.
- **Payload-level filtering in subscriptions.** Subscribers filter on
  `event.payload["to"]` in their handler code. Declarative payload
  filters (like EventBridge patterns) are deferred — the config-level
  filtering in keel-ai's `[extensions.ai]` is the right place for that.
- **Async/parallel execution.** Subscribers run sequentially.
- **`.d/` multi-file hook directories.** Single file per event.
