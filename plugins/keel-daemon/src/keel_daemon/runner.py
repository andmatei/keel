"""Entry point for the keel-daemon-run script.

Invoked as: keel-daemon-run <daemon_id> <workspace_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from keel_daemon.loader import load_daemons


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <daemon_id> <workspace_dir>", file=sys.stderr)
        sys.exit(1)

    daemon_id = sys.argv[1]
    workspace_dir = Path(sys.argv[2])

    daemons = load_daemons()
    if daemon_id not in daemons:
        print(f"error: daemon '{daemon_id}' not registered", file=sys.stderr)
        sys.exit(1)

    daemon_cls = daemons[daemon_id]
    daemon = daemon_cls()
    daemon.run(workspace_dir)


if __name__ == "__main__":
    main()
