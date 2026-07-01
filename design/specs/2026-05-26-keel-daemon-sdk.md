# keel-daemon SDK — Design Spec

**Status:** Decided, not yet implemented.

## Goal

Provide a base class and CLI support so first-party and third-party plugins can ship long-running background daemons that integrate naturally with the keel hook system.

Primary motivating use case: `keel-github` — a daemon that polls GitHub for merged PRs and calls `keel task done`, triggering the hook chain for rebase and Jira transitions.

---

## Decisions

### State sharing: Option B — shared state files

Each daemon owns a JSON state file under `.keel/daemons/<daemon-id>/state.json` within the relevant project or workspace directory. No IPC, no message bus. Daemons are single-process; parallelism is not a goal for v1.

Rejected alternatives:
- **Option A**: trigger-only (fire on `task.done` hook, no persistent daemon) — too reactive, can't poll external systems.
- **Option C**: full message bus / socket IPC — over-engineered for the current use cases; can be layered on later if needed.

### Location: `plugins/keel-daemon/` in the monorepo

Same pattern as `plugins/jira/`. Separate Python package (`keel-daemon`), installed alongside keel core. Core (`keel`) does **not** depend on `keel-daemon`; the plugin registers itself via entry points.

### Entry point group: `keel.daemons`

```toml
[project.entry-points."keel.daemons"]
my-daemon = "my_package.daemon:MyDaemon"
```

keel discovers all registered daemons at runtime by iterating this group (same pattern as `keel.event_listeners`, `keel.ticket_providers`).

---

## Base class contract

```python
class KeelingDaemon:
    id: str           # unique slug, used for state file path and log prefix
    interval: int     # tick interval in seconds (default: 30)

    # Lifecycle — override as needed
    def on_start(self) -> None: ...
    def on_tick(self) -> None: ...   # called every `interval` seconds
    def on_stop(self) -> None: ...

    # Provided by base class
    self.state: dict          # loaded from / persisted to state.json automatically
    self.emit(event, **kw)    # fire a keel hook event (e.g. "task.status")
    self.log(msg)             # structured log line prefixed with daemon id
```

`self.state` is loaded on `on_start` and auto-saved after every `on_tick`. Daemons should treat it as an in-memory dict; the SDK handles persistence.

---

## CLI commands (planned)

```
keel daemon list          # show all registered daemons and their status (running / stopped)
keel daemon start <id>    # start a daemon in the background (writes PID file)
keel daemon stop <id>     # graceful stop (SIGTERM)
keel daemon status <id>   # running, last tick timestamp, recent log lines
keel daemon logs <id>     # tail the daemon's log file
```

PID files live under `.keel/daemons/<id>/pid`. Log files under `.keel/daemons/<id>/daemon.log`.

---

## Relation to keel-github (Track 3)

`keel-github` will be the first consumer of this SDK. Its daemon:
1. Polls GitHub for PR merges on branches recorded in `milestones.toml`.
2. On merge: calls `self.emit("task.status", ...)` to trigger `keel task done`.
3. The `task.done` hook chain handles: marking task done in TOML, triggering rebase of downstream stacked branches, transitioning Jira ticket.

`keel-github` is **parked** until `keel-daemon` SDK is implemented.

---

## Next step

Implement `plugins/keel-daemon/` — `KeelingDaemon` base class, state persistence, `keel daemon` CLI subcommand group.
