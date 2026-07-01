"""Plugin entry-point loader for keel.daemons.

A plugin declares its daemons via:

    [project.entry-points."keel.daemons"]
    my-daemon = "my_pkg.daemon:MyDaemon"

Each entry-point value imports a KeelingDaemon subclass.
Loading is idempotent because Python's import machinery caches modules.
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points

from keel_daemon.daemon import KeelingDaemon

ENTRY_POINT_GROUP = "keel.daemons"


def load_daemons() -> dict[str, type[KeelingDaemon]]:
    """Discover all registered daemon classes.

    Returns a dict mapping daemon id → daemon class.
    Errors loading any entry point are printed to stderr but never raised.
    """
    daemons: dict[str, type[KeelingDaemon]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            daemon_cls = ep.load()
            daemons[daemon_cls.id] = daemon_cls
        except Exception as e:
            print(
                f"warning: failed to load daemon '{ep.name}': {e}",
                file=sys.stderr,
            )
    return daemons
