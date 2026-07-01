"""Tests for KeelingDaemon base class."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from keel_daemon.daemon import KeelingDaemon


class _TestDaemon(KeelingDaemon):
    id = "test-daemon"


def _make_daemon(tmp_path: Path) -> _TestDaemon:
    d = _TestDaemon()
    d._workspace_dir = tmp_path
    return d


def test_state_save_and_load(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._daemon_dir.mkdir(parents=True, exist_ok=True)

    daemon.state = {"key": "value", "count": 42}
    daemon._save_state()

    expected_file = tmp_path / ".keel" / "daemons" / "test-daemon" / "state.json"
    assert expected_file.exists()

    daemon2 = _make_daemon(tmp_path)
    daemon2._load_state()
    assert daemon2.state == {"key": "value", "count": 42}


def test_load_state_missing_file(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    # No state file exists; _daemon_dir doesn't exist either, but _load_state checks
    # existence before reading.
    daemon._load_state()
    assert daemon.state == {}


def test_load_state_corrupt_file(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._daemon_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".keel" / "daemons" / "test-daemon" / "state.json").write_text("not-json")

    daemon._load_state()
    assert daemon.state == {}


def test_log_appends_to_file(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._daemon_dir.mkdir(parents=True, exist_ok=True)

    daemon.log("hello world")

    log_contents = daemon._log_file.read_text()
    assert "hello world" in log_contents
    assert "[test-daemon]" in log_contents


def test_emit_calls_dispatcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def fake_dispatch(event, *, out, workspace_dir, project_dir) -> None:
        calls.append((event, out, workspace_dir, project_dir))

    # Also monkeypatch the lazy import inside emit() by pre-seeding the module attr
    # The emit() method does `from keel.hooks.dispatcher import dispatch` internally.
    # We patch via the module-level reference by injecting into keel_daemon.daemon's namespace.
    import keel.hooks.dispatcher as dispatcher_module

    monkeypatch.setattr(dispatcher_module, "dispatch", fake_dispatch)

    daemon = _make_daemon(tmp_path)
    daemon._daemon_dir.mkdir(parents=True, exist_ok=True)

    daemon.emit("task.status", project="myproj", id="task-1")

    assert len(calls) == 1
    event, _out, _ws, _proj = calls[0]
    assert event.entity == "task"
    assert event.action == "status"
    assert event.phase == "post"
    assert event.project == "myproj"


def test_run_calls_lifecycle_methods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # signal.signal() only works in the main thread, so we patch it out.
    import signal as signal_mod

    monkeypatch.setattr(signal_mod, "signal", lambda signum, handler: None)

    calls: list[str] = []

    class _LifecycleDaemon(KeelingDaemon):
        id = "lifecycle-daemon"
        interval = 1

        def on_start(self) -> None:
            calls.append("on_start")

        def on_tick(self) -> None:
            calls.append("on_tick")
            # Stop after first tick so run() exits promptly.
            self._running = False

        def on_stop(self) -> None:
            calls.append("on_stop")

    daemon = _LifecycleDaemon()

    # Run in a thread so the test isn't blocked if something goes wrong.
    t = threading.Thread(target=daemon.run, args=(tmp_path,))
    t.start()
    t.join(timeout=5)

    assert not t.is_alive(), "daemon.run() did not exit within 5 seconds"
    assert "on_start" in calls
    assert "on_tick" in calls
    assert "on_stop" in calls
