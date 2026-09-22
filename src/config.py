# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
config.py — Application-wide constants and default settings.
"""
from __future__ import annotations

import os
import sys

# ── Application identifiers ───────────────────────────────────────────
APP_ID   = "io.github.AbuKaram01.KaramTC"
APP_NAME = "KaramTC"
VERSION  = "0.1.0"

# ── Supported image formats ───────────────────────────────────────────
SUPPORTED_MIME = ("image/jpeg", "image/png", "image/webp")
SUPPORTED_EXT  = (".jpg", ".jpeg", ".png", ".webp")

PDF_SUPPORTED_EXT       = (".pdf",)
BOOK_IMAGE_DPI          = 200   # default; user-adjustable in OCR Settings (pdf_image_dpi)
BOOK_IMAGE_JPEG_QUALITY = 85    # default; user-adjustable in OCR Settings (pdf_jpeg_quality)

# Accepted ranges for the two settings above (inclusive). Values outside them —
# e.g. from a hand-edited settings.json — are clamped, never trusted.
BOOK_IMAGE_DPI_RANGE          = (100, 600)
BOOK_IMAGE_JPEG_QUALITY_RANGE = (50, 100)

# ── Provider identifiers ──────────────────────────────────────────────
PROVIDER_TESSERACT = "tesseract"


# ── Where the user's folders are ──────────────────────────────────────
def _on_windows() -> bool:
    return sys.platform == "win32"


def fallback_base_dir(kind: str) -> str:
    """
    The folder GLib would report for *kind* ("data" or "config"), worked out
    without GLib, for when GTK cannot be imported (the tests that run without
    it, a console-less start that has not found the runtime yet).

    Windows: %LOCALAPPDATA% for data and %APPDATA% for settings (where GLib puts
    them). Elsewhere: the XDG defaults, ~/.local/share and ~/.config. The
    XDG_*_HOME variables are not read here; callers that honour them do so first.
    """
    if kind not in ("data", "config"):
        raise ValueError(f"unknown kind of folder: {kind!r}")
    home = os.path.expanduser("~")
    if _on_windows():
        if kind == "data":
            return os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    if kind == "data":
        return os.path.join(home, ".local", "share")
    return os.path.join(home, ".config")


# ── Where downloaded data lives ───────────────────────────────────────
def user_data_dir() -> str:
    """
    The folder for data the app downloads or generates (OCR language packs,
    the speech model, saved transcription progress): the XDG data directory
    plus the application id. Resolved lazily so GTK need not be imported at
    module load time.
    """
    try:
        from gi.repository import GLib
        base = GLib.get_user_data_dir()
    except Exception:
        base = fallback_base_dir("data")
    return os.path.join(base, APP_ID)
