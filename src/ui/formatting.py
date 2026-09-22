# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/formatting.py — Human-readable sizes and durations.
"""
from __future__ import annotations

_KB, _MB, _GB = 1024, 1024**2, 1024**3


def format_bytes(size: int) -> str:
    if size >= _GB:
        return f"{size / _GB:.1f} GB"
    if size >= _MB:
        return f"{size / _MB:.1f} MB"
    return f"{max(size, 0) / _KB:.0f} KB"


def format_duration(seconds: float) -> str:
    """H:MM:SS, or M:SS under an hour."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_remaining(seconds: float) -> str:
    """A rough time left, for an ETA: "under a minute", "about 5 min", "about 1 h 20 min"."""
    minutes = round(seconds / 60)
    if seconds < 60:
        return "under a minute"
    if minutes < 60:
        return f"about {minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"about {hours} h {minutes:02d} min" if minutes else f"about {hours} h"
