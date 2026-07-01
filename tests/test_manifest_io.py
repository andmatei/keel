"""Tests for atomic_write in keel.io."""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from keel.io import atomic_write


def test_atomic_write_preserves_permissions(tmp_path: Path) -> None:
    """Overwriting an existing file preserves its permissions."""
    target = tmp_path / "manifest.toml"
    target.write_text("old")
    target.chmod(0o640)

    atomic_write(target, "new")

    assert target.read_text() == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_atomic_write_cleans_up_on_failure(tmp_path: Path) -> None:
    """If the write fails, no temp file is left behind."""
    target = tmp_path / "manifest.toml"
    target.write_text("original")

    with patch("keel.io.open", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            atomic_write(target, "new content")

    assert target.read_text() == "original"
    temps = list(tmp_path.glob("*.tmp"))
    assert temps == []
