"""Tests for process management functions."""
from __future__ import annotations

from pathlib import Path

from keel_daemon.process import daemon_dir, is_running, log_file, pid_file, read_recent_logs


def test_daemon_dir(tmp_path: Path) -> None:
    assert daemon_dir(tmp_path, "my-daemon") == tmp_path / ".keel" / "daemons" / "my-daemon"


def test_pid_file(tmp_path: Path) -> None:
    assert pid_file(tmp_path, "my-daemon") == tmp_path / ".keel" / "daemons" / "my-daemon" / "pid"


def test_log_file(tmp_path: Path) -> None:
    expected = (
        tmp_path / ".keel" / "daemons" / "my-daemon" / "daemon.log"
    )
    assert log_file(tmp_path, "my-daemon") == expected


def test_is_running_no_pid_file(tmp_path: Path) -> None:
    assert is_running("my-daemon", tmp_path) is False


def test_is_running_stale_pid(tmp_path: Path) -> None:
    pid_file(tmp_path, "my-daemon").parent.mkdir(parents=True, exist_ok=True)
    pid_file(tmp_path, "my-daemon").write_text("999999999")

    assert is_running("my-daemon", tmp_path) is False


def test_read_recent_logs_no_file(tmp_path: Path) -> None:
    assert read_recent_logs("my-daemon", tmp_path) == []


def test_read_recent_logs_last_n(tmp_path: Path) -> None:
    lf = log_file(tmp_path, "my-daemon")
    lf.parent.mkdir(parents=True, exist_ok=True)
    lf.write_text("".join(f"line-{i}\n" for i in range(30)))

    result = read_recent_logs("my-daemon", tmp_path, n=10)
    assert len(result) == 10
    assert "line-29" in result[-1]
