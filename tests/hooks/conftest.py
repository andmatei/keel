"""Shared fixtures for hook tests."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest


@pytest.fixture
def make_executable_script():
    """Create an executable script file."""
    def _make(path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return _make
