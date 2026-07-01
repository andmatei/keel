# keel-daemon SDK — Implementation Plan

**Spec:** `design/specs/2026-05-26-keel-daemon-sdk.md`
**Target:** `plugins/keel-daemon/` in the keel monorepo at `/Users/andrei.matei/projects/keel/`

## Context

- Pattern ref for plugin structure: `plugins/jira/` (separate Python package, entry points)
- Pattern ref for hook loader: `src/keel/hooks/loader.py`
- Pattern ref for CLI commands: `src/keel/commands/task/`
- Pattern ref for Typer app: `src/keel/app.py`
- Root pyproject.toml already uses `members = ["plugins/*"]` glob — no change needed there for uv workspace membership
- Entry point group for CLI: `keel.commands` (see `app.py::_load_plugin_commands`)
- New entry point group: `keel.daemons` (for daemon class discovery)

## Task 1 — Plugin package scaffolding

Create the `plugins/keel-daemon/` package structure.

**Files to create:**

`plugins/keel-daemon/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling>=1.21"]
build-backend = "hatchling.build"

[project]
name = "keel-daemon"
version = "0.0.1"
description = "Long-running background daemon SDK for keel plugins."
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
authors = [{ name = "Andrei Matei" }]
keywords = ["keel", "daemon", "plugin"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX",
    "Operating System :: MacOS",
    "Topic :: Software Development",
]
dependencies = [
    "keel-cli>=0.0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "ruff>=0.6",
]

[project.scripts]
keel-daemon-run = "keel_daemon.runner:main"

[project.entry-points."keel.commands"]
daemon = "keel_daemon.cli:register"

[tool.hatch.build.targets.wheel]
packages = ["src/keel_daemon"]

[tool.uv.sources]
keel-cli = { workspace = true }

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ANN", "RUF"]
ignore = ["ANN401"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN", "S101"]
```

`plugins/keel-daemon/src/keel_daemon/__init__.py`:
```python
"""keel-daemon — long-running background daemon SDK for keel plugins."""
```

`plugins/keel-daemon/tests/__init__.py`: empty

`plugins/keel-daemon/tests/conftest.py`:
```python
"""Test fixtures for keel-daemon tests."""
from __future__ import annotations

import pytest
```

**Root `pyproject.toml` change** — add to `[tool.uv.sources]`:
```toml
keel-daemon = { workspace = true }
```

And add to `[project.optional-dependencies]` `all`:
```toml
all = ["keel-jira>=0.0.2", "keel-daemon>=0.0.1"]
```

## Task 2 — KeelingDaemon base class

Create `plugins/keel-daemon/src/keel_daemon/daemon.py`.

The `KeelingDaemon` abstract base class:
- Class-level `id: str` (must be overridden) and `interval: int = 30`
- Instance `self.state: dict` — in-memory dict, auto-loaded on start and auto-saved after every tick
- `self._workspace_dir: Path` — set when `run()` is called
- `self._daemon_dir: Path` — `.keel/daemons/<id>/` inside workspace_dir
- `_load_state()` / `_save_state()` — JSON read/write of `.keel/daemons/<id>/state.json`
- `on_start()`, `on_tick()`, `on_stop()` — default no-op, override as needed
- `emit(event_name: str, project: str | None = None, deliverable: str | None = None, **payload)` — creates a `HookEvent` (entity=parts[0], action=parts[1], phase="post") and calls `keel.hooks.dispatcher.dispatch()`; uses a plain `Output()` and the daemon's `workspace_dir`
- `log(msg: str)` — writes `<ISO timestamp> [<id>] msg\n` to `.keel/daemons/<id>/daemon.log`
- `run(workspace_dir: Path)` — main loop:
  1. Set `self._workspace_dir`, set up `self._daemon_dir`, mkdir
  2. `_load_state()`
  3. Register SIGTERM/SIGINT handler that sets `self._running = False`
  4. `self._running = True`, call `on_start()`
  5. Loop: `on_tick()`, `_save_state()`, then sleep `interval` seconds (in 1s increments, breaking early if `not self._running`)
  6. `on_stop()`

## Task 3 — Process management

Create `plugins/keel-daemon/src/keel_daemon/process.py`.

Functions:
- `daemon_dir(workspace_dir: Path, daemon_id: str) -> Path` — `.keel/daemons/<daemon_id>/`
- `pid_file(workspace_dir: Path, daemon_id: str) -> Path` — `<daemon_dir>/pid`
- `log_file(workspace_dir: Path, daemon_id: str) -> Path` — `<daemon_dir>/daemon.log`
- `start_daemon(daemon_id: str, workspace_dir: Path) -> int` — launches `keel-daemon-run <daemon_id> <workspace_dir>` as a detached subprocess (new session, stdout/stderr redirected to log file), writes PID, returns PID
- `stop_daemon(daemon_id: str, workspace_dir: Path) -> None` — reads PID file, sends SIGTERM, removes PID file
- `is_running(daemon_id: str, workspace_dir: Path) -> bool` — checks if PID file exists and process is alive (via `os.kill(pid, 0)`)
- `read_recent_logs(daemon_id: str, workspace_dir: Path, n: int = 20) -> list[str]` — reads last n lines from daemon.log

## Task 4 — Daemon loader + runner

Create `plugins/keel-daemon/src/keel_daemon/loader.py`:
- `ENTRY_POINT_GROUP = "keel.daemons"`
- `load_daemons() -> dict[str, type[KeelingDaemon]]` — iterates entry points, loads each, returns `{daemon.id: daemon_cls}` dict. Errors are printed to stderr but never raised (same pattern as hooks/loader.py).

Create `plugins/keel-daemon/src/keel_daemon/runner.py`:
- `main()` — called by `keel-daemon-run <daemon_id> <workspace_dir>` script:
  1. Parse `sys.argv[1]` (daemon_id) and `sys.argv[2]` (workspace_dir)
  2. `load_daemons()` to get class
  3. Instantiate and call `daemon.run(workspace_dir)`

## Task 5 — CLI commands

Create `plugins/keel-daemon/src/keel_daemon/commands/__init__.py`:
```python
import typer
app = typer.Typer(name="daemon", help="Manage long-running background daemons.", no_args_is_help=True)
# import and register subcommands
```

Create these command files:

`commands/list.py` — `cmd_list`:
- Load all registered daemons via `load_daemons()`
- For each daemon: check `is_running()` to get status
- Display table: id, status (running/stopped), interval
- Supports `--json`

`commands/start.py` — `cmd_start(id: str)`:
- Load daemons, resolve workspace_dir from CWD
- Check not already running
- Call `start_daemon(id, workspace_dir)`
- Output: "Daemon <id> started (pid: <N>)"

`commands/stop.py` — `cmd_stop(id: str)`:
- Load daemons, resolve workspace_dir from CWD
- Check is running
- Call `stop_daemon(id, workspace_dir)`
- Output: "Daemon <id> stopped"

`commands/status.py` — `cmd_status(id: str)`:
- Show running/stopped, PID if running, last tick from recent log lines
- Supports `--json`

`commands/logs.py` — `cmd_logs(id: str, n: int = typer.Option(20, "-n"))`:
- Read and print recent log lines

Create `plugins/keel-daemon/src/keel_daemon/cli.py`:
```python
import typer
from keel_daemon.commands import app as daemon_app

def register(main_app: typer.Typer) -> None:
    main_app.add_typer(daemon_app, name="daemon")
```

## Task 6 — Tests

Create `plugins/keel-daemon/tests/test_daemon.py`:
- Test that `KeelingDaemon` subclass with `on_tick` called updates state
- Test `_load_state` / `_save_state` round-trip (uses tmp_path)
- Test `log()` appends to daemon.log with timestamp prefix
- Test `emit()` calls keel's dispatcher (mock the dispatcher)
- Test that `run()` calls on_start, on_tick (at least once), on_stop when stopped via signal

Create `plugins/keel-daemon/tests/test_process.py`:
- Test `is_running()` returns False when no PID file
- Test `read_recent_logs()` returns empty list when no log file
- Test `read_recent_logs()` returns correct last-n lines

Create `plugins/keel-daemon/tests/test_cli.py`:
- Test `keel daemon list` with no daemons registered shows empty output
- Test `keel daemon status <id>` on unknown daemon gives error

## Task 7 — Integration: update plugin list

Update `src/keel/commands/plugin/list.py`:
- Add `"keel.daemons"` to the `GROUPS` list

This makes `keel plugin list` show registered daemon entry points alongside commands, ticket_providers, event_listeners, and lifecycles.
