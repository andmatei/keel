"""Low-level I/O helpers."""

import os
import stat
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via temp-file + rename.

    Preserves the original file's permissions if it exists; otherwise
    uses the default mode from the process umask.
    """
    orig_mode: int | None = None
    if path.exists():
        orig_mode = stat.S_IMODE(path.stat().st_mode)

    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        if orig_mode is not None:
            os.fchmod(fd, orig_mode)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.fchmod(fd, 0o666 & ~umask)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
