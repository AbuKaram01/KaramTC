# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Application-wide constants, default settings and the locations of the per-user folders."""

from __future__ import annotations

import os
import sys

# --- Application identifiers ---
APP_ID   = "io.github.AbuKaram01.KaramTC"
APP_NAME = "KaramTC"
VERSION  = "0.1.0"

# --- Supported input formats ---
SUPPORTED_MIME = ("image/jpeg", "image/png", "image/webp")
SUPPORTED_EXT  = (".jpg", ".jpeg", ".png", ".webp")

PDF_SUPPORTED_EXT       = (".pdf",)
# Defaults for the resolution and JPEG quality of the page images rendered from a PDF. Both are adjustable by the
# user in the OCR settings (pdf_image_dpi and pdf_jpeg_quality).
BOOK_IMAGE_DPI          = 200
BOOK_IMAGE_JPEG_QUALITY = 85

# Accepted ranges (inclusive) for the two settings above. Values outside them, for example from a hand-edited
# settings.json, are clamped and never trusted.
BOOK_IMAGE_DPI_RANGE          = (100, 600)
BOOK_IMAGE_JPEG_QUALITY_RANGE = (50, 100)

# --- Provider identifiers ---
PROVIDER_TESSERACT = "tesseract"


# --- Per-user folders ---
def _on_windows() -> bool:
    return sys.platform == "win32"


def fallback_base_dir(kind: str) -> str:
    """Return the folder GLib would report for *kind* ("data" or "config"), computed without GLib.

    This is the fallback for when GTK cannot be imported: tests that run without it, or a console-less start that
    has not located the runtime yet.

    On Windows the data folder is %LOCALAPPDATA% and the settings folder is %APPDATA%, which is where GLib puts
    them. Elsewhere the XDG defaults ~/.local/share and ~/.config apply. The XDG_*_HOME variables are not read
    here; callers that honour them do so before calling this function.

    Raises:
        ValueError: *kind* is neither "data" nor "config".
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


# --- Downloaded data ---
def user_data_dir() -> str:
    """Return the folder for data the app downloads or generates, below the XDG data directory.

    This covers the OCR language packs, the speech model and the saved transcription progress. The folder is the
    XDG data directory plus the application id. It is resolved lazily so that GTK need not be imported when this
    module is loaded.
    """
    try:
        from gi.repository import GLib
        base = GLib.get_user_data_dir()
    except Exception:
        base = fallback_base_dir("data")
    return os.path.join(base, APP_ID)
