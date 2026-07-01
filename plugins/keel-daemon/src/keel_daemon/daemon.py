"""KeelingDaemon — abstract base class for keel background daemons."""

from __future__ import annotations

import json
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class KeelingDaemon:
    """Base class for long-running keel daemons.

    Subclasses must define ``id`` as a class variable. Override ``on_start``,
    ``on_tick``, and ``on_stop`` as needed. The base class handles state
    persistence, signal handling, and hook dispatch.
    """

    id: str
    interval: int = 30

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self._workspace_dir: Path | None = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle hooks — override as needed
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Called once after state is loaded, before the tick loop begins."""

    def on_tick(self) -> None:
        """Called every ``interval`` seconds."""

    def on_stop(self) -> None:
        """Called once after the tick loop exits."""

    # ------------------------------------------------------------------
    # Internal path properties
    # ------------------------------------------------------------------

    @property
    def _daemon_dir(self) -> Path:
        assert self._workspace_dir is not None
        return self._workspace_dir / ".keel" / "daemons" / self.id

    @property
    def _state_file(self) -> Path:
        return self._daemon_dir / "state.json"

    @property
    def _log_file(self) -> Path:
        return self._daemon_dir / "daemon.log"

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        if not self._state_file.exists():
            self.state = {}
            return
        try:
            self.state = json.loads(self._state_file.read_text())
        except json.JSONDecodeError:
            self.state = {}

    def _save_state(self) -> None:
        self._daemon_dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self.state))

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, msg: str) -> None:
        """Append a timestamped log line to the daemon's log file."""
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).isoformat()
        with self._log_file.open("a") as fh:
            fh.write(f"{ts} [{self.id}] {msg}\n")

    # ------------------------------------------------------------------
    # Hook dispatch
    # ------------------------------------------------------------------

    def emit(
        self,
        event_name: str,
        project: str | None = None,
        deliverable: str | None = None,
        positional_args: tuple[str, ...] = (),
        **payload: Any,
    ) -> None:
        """Fire a keel hook event.

        ``event_name`` must be in ``"entity.action"`` form (e.g. ``"task.status"``).
        """
        parts = event_name.split(".")
        if len(parts) != 2:
            raise ValueError(f"event_name must be 'entity.action', got {event_name!r}")

        from keel.hooks.dispatcher import dispatch
        from keel.hooks.types import HookEvent
        from keel.output import Output

        event = HookEvent(
            entity=parts[0],
            action=parts[1],
            phase="post",
            project=project,
            deliverable=deliverable,
            payload=payload,
            positional_args=positional_args,
        )
        dispatch(event, out=Output(), workspace_dir=self._workspace_dir, project_dir=None)

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _handle_stop(self, signum: int, frame: object) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, workspace_dir: Path) -> None:
        """Start the daemon loop.

        Blocks until SIGTERM or SIGINT is received. State is loaded on start
        and saved after every tick.
        """
        self._workspace_dir = workspace_dir
        self._daemon_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT, self._handle_stop)

        self._running = True
        self.log(f"starting (interval={self.interval}s)")
        self.on_start()

        while self._running:
            self.on_tick()
            self._save_state()
            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

        self.on_stop()
        self.log("stopped")
