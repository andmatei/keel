from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


def daemon_dir(workspace_dir: Path, daemon_id: str) -> Path:
    """Returns .keel/daemons/<daemon_id>/ inside the workspace."""
    return workspace_dir / ".keel" / "daemons" / daemon_id


def pid_file(workspace_dir: Path, daemon_id: str) -> Path:
    return daemon_dir(workspace_dir, daemon_id) / "pid"


def log_file(workspace_dir: Path, daemon_id: str) -> Path:
    return daemon_dir(workspace_dir, daemon_id) / "daemon.log"


def start_daemon(daemon_id: str, workspace_dir: Path) -> int:
    """Launch daemon as a detached subprocess. Returns PID.

    Runs: `python -m keel_daemon.runner <daemon_id> <workspace_dir>`
    as a new session (detached), stdout/stderr redirected to the daemon's log file.
    Writes PID to pid_file.
    """
    daemon_dir(workspace_dir, daemon_id).mkdir(parents=True, exist_ok=True)
    with open(log_file(workspace_dir, daemon_id), "a") as log_fd:
        proc = subprocess.Popen(
            [sys.executable, "-m", "keel_daemon.runner", daemon_id, str(workspace_dir)],
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file(workspace_dir, daemon_id).write_text(str(proc.pid))
    return proc.pid


def stop_daemon(daemon_id: str, workspace_dir: Path) -> None:
    """Send SIGTERM to the daemon process and remove the PID file.

    Raises FileNotFoundError if no PID file (daemon not started).
    Raises ProcessLookupError if the process is not running (stale PID).
    """
    pf = pid_file(workspace_dir, daemon_id)
    pid = int(pf.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    pf.unlink(missing_ok=True)


def is_running(daemon_id: str, workspace_dir: Path) -> bool:
    """Check if the daemon is running. Returns False if no PID file or process is dead."""
    pf = pid_file(workspace_dir, daemon_id)
    if not pf.exists():
        return False
    pid = int(pf.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists, just not owned by us
    return True


def read_recent_logs(daemon_id: str, workspace_dir: Path, n: int = 20) -> list[str]:
    """Return the last n lines from the daemon's log file. Returns [] if no log file."""
    lf = log_file(workspace_dir, daemon_id)
    if not lf.exists():
        return []
    return lf.read_text().splitlines()[-n:]
