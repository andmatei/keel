"""Tag display helpers — deterministic coloring and Rich formatting."""

from __future__ import annotations

import zlib

_TAG_PALETTE = [
    "bright_cyan",
    "bright_green",
    "bright_magenta",
    "bright_yellow",
    "dodger_blue2",
    "dark_orange",
    "medium_purple1",
    "spring_green1",
]


def tag_color(name: str) -> str:
    """Return a Rich style string for *name*, deterministic across runs."""
    return _TAG_PALETTE[zlib.crc32(name.encode()) % len(_TAG_PALETTE)]


def format_tags(tags: list[str]) -> str:
    """Return a Rich-markup string rendering *tags* with deterministic colors.

    Returns empty string when tags is empty (caller can skip rendering).
    """
    if not tags:
        return ""
    parts = [f"[{tag_color(t)}]{t}[/{tag_color(t)}]" for t in tags]
    return ", ".join(parts)
