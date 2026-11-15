# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Find the tesseract program and start it quietly.

On Linux the program is simply "tesseract" on PATH. Tesseract's Windows installers do not add themselves to PATH, so
there it is also looked for in the folder they use. A program started by a GUI application with no console of its own
would flash a black console window for every page, so on Windows it is started with CREATE_NO_WINDOW.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from config import APP_ID, fallback_base_dir
from providers.tesseract import ascii_paths

# The program's name as found on PATH.
PROGRAM = "tesseract"
_CREATE_NO_WINDOW = 0x08000000


def is_windows() -> bool:
    """Return True on Windows."""
    return sys.platform == "win32"


def bundled_candidates() -> list[str]:
    """Return the copies of tesseract.exe that belong to KaramTC.

    These are the one the Windows installer puts beside the program, and the one the install script unpacks into the
    data folder.
    """
    program_folder = Path(__file__).resolve().parents[3]
    data_folder = Path(os.environ.get("XDG_DATA_HOME") or fallback_base_dir("data")) / APP_ID
    return [str(program_folder / "tesseract" / "tesseract.exe"), str(data_folder / "tesseract" / "tesseract.exe")]


def bundled_path() -> str | None:
    """Return KaramTC's own tesseract.exe, or None (always None outside Windows)."""
    if not is_windows():
        return None
    return next((path for path in bundled_candidates() if os.path.isfile(path)), None)


def windows_install_candidates() -> list[str]:
    """Return the places where the Windows installers put tesseract.exe."""
    folders = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.path.join(os.environ["LOCALAPPDATA"], "Programs") if os.environ.get("LOCALAPPDATA") else None,
    ]
    return [os.path.join(folder, "Tesseract-OCR", "tesseract.exe") for folder in folders if folder]


def windows_install_path() -> str | None:
    """Return tesseract.exe in the installer's folder, or None (always None outside Windows)."""
    if not is_windows():
        return None
    return next((path for path in windows_install_candidates() if os.path.isfile(path)), None)


def find_tesseract() -> str | None:
    """Return the path of the tesseract program, or None if there is none.

    On Windows KaramTC's own copy comes first (a known version, whatever else is on the machine), then PATH, then the
    folder the Tesseract installers use; elsewhere it is whatever is on PATH.
    """
    return bundled_path() or shutil.which(PROGRAM) or windows_install_path()


def program() -> str:
    """Return what to run: a full path, or just "tesseract".

    A full path is returned for KaramTC's own copy and for one known only from the installer's folder. A path with
    non-ASCII letters (a user name in Arabic) is given in its short 8.3 form, since Tesseract works out where its
    language data is from the path it was started with.
    """
    if is_windows():
        bundled = bundled_path()
        if bundled:
            return ascii_paths.launchable(bundled)
        if not shutil.which(PROGRAM):
            installed = windows_install_path()
            return ascii_paths.launchable(installed) if installed else PROGRAM
    return PROGRAM


def quiet_window_options() -> dict:
    """Return the subprocess options that keep a console window from appearing (none outside Windows)."""
    return {"creationflags": _CREATE_NO_WINDOW} if is_windows() else {}
