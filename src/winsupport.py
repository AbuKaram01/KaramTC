# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

r"""Windows start-up support: what KaramTC needs before GTK can be imported.

main.py calls this first thing, and only on Windows. The module does not import GTK itself (its purpose is to make
that import possible), so it stays usable from the install script's "does GTK load?" check.

* prepare_runtime() first loads the Visual C++ runtime DLLs that the installer carries (<application
  folder>\vcruntime), so that ctranslate2 and onnxruntime (the Audio/Video tab) load on a computer without the
  Visual C++ Redistributable. It then tells Python and the dynamic linker where the GTK 4 + libadwaita runtime is:
  the folder in KARAMTC_GTK_DIR, else the one that came inside the installer (<application folder>\gtk, beside the
  .venv), else the one scripts/install-windows.ps1 downloads by default (<data folder>\gtk, the folder GLib reports
  as the application's data folder).
* log_errors_without_a_console() gives a program started with pythonw.exe (the Start menu entry) somewhere to write
  its errors: it has no console, so they would vanish.
"""
from __future__ import annotations

import os
import sys
import time

from config import APP_ID, fallback_base_dir

GTK_DIR_VARIABLE = "KARAMTC_GTK_DIR"
LOG_FILE_NAME = "karamtc.log"
# A log bigger than this is started afresh rather than growing forever.
_LOG_LIMIT_BYTES = 1_000_000

# os.add_dll_directory() hands back an object; keep it so that the folder stays registered.
_dll_directories: list = []
# Libraries loaded by hand (the Visual C++ runtime): kept for as long as the process lives.
_loaded_runtime: list = []


def is_windows() -> bool:
    """Return True when running on Windows."""
    return sys.platform == "win32"


def data_folder() -> str:
    """Return the application's data folder, as GLib reports it (found without GLib, which cannot be loaded yet)."""
    return os.path.join(os.environ.get("XDG_DATA_HOME") or fallback_base_dir("data"), APP_ID)


def application_folder() -> str:
    """Return the folder of the installation: the parent of the virtual environment.

    It is the folder that holds ``.venv``, ``src`` and ``gtk``.
    """
    return os.path.dirname(os.path.abspath(sys.prefix))


def runtime_candidates() -> list[str]:
    """Return the folders where a GTK runtime may be, best first.

    In order: the folder that was named (KARAMTC_GTK_DIR), the one inside the installer, the downloaded one.
    """
    named = os.environ.get(GTK_DIR_VARIABLE)
    candidates = [named] if named else []
    candidates += [os.path.join(application_folder(), "gtk"), os.path.join(data_folder(), "gtk")]
    return candidates


def runtime_folder() -> str | None:
    """Return the GTK runtime folder (the one holding bin, lib and share), or None if there is none."""
    for candidate in runtime_candidates():
        if os.path.isdir(os.path.join(candidate, "bin")):
            return candidate
    return None


def _put_first(variable: str, folder: str) -> None:
    """Put *folder* at the front of the path-list environment variable *variable*."""
    current = os.environ.get(variable)
    os.environ[variable] = folder + os.pathsep + current if current else folder


def prepare_runtime() -> str | None:
    """Make the bundled Visual C++ runtime and the GTK runtime's DLLs and typelibs findable by this process.

    Run before GTK is loaded, so that the GTK import (and, later, the ctranslate2 and onnxruntime imports) works
    afterwards. Does nothing outside Windows.

    Returns:
        The GTK runtime folder, or None when nothing was done for GTK (not Windows, or no runtime found: the import
        then fails with its own message, which log_errors_without_a_console keeps for a console-less start).
    """
    if not is_windows():
        return None
    # First, because GTK's own DLLs may need msvcp140.dll too.
    vcruntime = find_vcruntime()
    if vcruntime is not None:
        configure_vcruntime(vcruntime)
    root = runtime_folder()
    if root is None:
        return None
    bin_folder = os.path.join(root, "bin")
    # Python 3.8+ looks for the DLLs that an extension module needs only in folders registered with
    # add_dll_directory (PATH is no longer searched for them), but the runtime's own helper programs
    # and plugins still rely on PATH. A folder that cannot be registered is still put on PATH.
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        try:
            _dll_directories.append(add_dll_directory(bin_folder))
        except OSError:
            pass
    _put_first("PATH", bin_folder)
    typelibs = os.path.join(root, "lib", "girepository-1.0")
    if os.path.isdir(typelibs):
        _put_first("GI_TYPELIB_PATH", typelibs)
    return root


# --- The Visual C++ runtime ---

def find_vcruntime() -> str | None:
    """Return the folder of Visual C++ runtime DLLs that the installer carries, or None if there is none.

    It is the ``vcruntime`` folder inside the application folder; it counts only if it holds at least one DLL.
    """
    folder = os.path.join(application_folder(), "vcruntime")
    try:
        has_libraries = any(name.lower().endswith(".dll") for name in os.listdir(folder))
    except OSError:
        return None
    return folder if has_libraries else None


def _load_library(path: str) -> None:
    """Load the DLL at *path* and keep it loaded for as long as the process lives."""
    import ctypes

    # Loaded by full path: what the DLL itself needs is looked for beside it too.
    _loaded_runtime.append(ctypes.WinDLL(path))


def configure_vcruntime(folder: str) -> list[str]:
    """Make this process use the Visual C++ runtime DLLs of *folder* (msvcp140.dll, vcomp140.dll ...).

    ctranslate2 and onnxruntime import msvcp140.dll, which only a computer that has the Visual C++ Redistributable
    has; the installer carries copies. They are loaded here, before any of those libraries is imported: a library
    loaded later finds a DLL of that name already in the process and uses it, so the copy that came with KaramTC is
    the one that runs, on a computer with or without the Redistributable (and one with an older Redistributable
    cannot give a library a runtime that is too old for it).

    The folder is also made known for DLLs that are looked up later and for programs started from here. Python's own
    vcruntime140.dll is not part of it: python.exe already has it loaded.

    Returns:
        The names of the DLLs that were loaded. One that cannot be loaded is skipped, leaving the system to supply
        it (or not).
    """
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        try:
            _dll_directories.append(add_dll_directory(folder))
        except OSError:
            pass
    _put_first("PATH", folder)
    try:
        # Case-insensitive, so that msvcp140.dll comes before msvcp140_1.dll.
        names = sorted((name for name in os.listdir(folder) if name.lower().endswith(".dll")), key=str.lower)
    except OSError:
        return []
    loaded: list[str] = []
    for name in names:
        if name.lower().startswith("vcruntime"):
            # python.exe has its own loaded; a second copy would be a second C runtime.
            continue
        try:
            _load_library(os.path.join(folder, name))
        except OSError:
            continue
        loaded.append(name)
    return loaded


def log_path() -> str:
    """Return the path of the log file written by log_errors_without_a_console."""
    return os.path.join(data_folder(), LOG_FILE_NAME)


def _redirect_c_streams(stream) -> None:
    """Point the process's own stdout/stderr at *stream*, so that what GLib and GTK print from C ends up there too."""
    for descriptor in (1, 2):
        try:
            os.dup2(stream.fileno(), descriptor)
        except OSError:
            pass


def log_errors_without_a_console() -> bool:
    """Send everything the program prints to karamtc.log when there is no console.

    pythonw.exe leaves sys.stdout and sys.stderr as None; in that case everything the program prints, tracebacks
    included, is appended to karamtc.log in the data folder.

    Returns:
        True if the log is now in use. Nothing is done with a console, or outside Windows.
    """
    if not is_windows() or (sys.stdout is not None and sys.stderr is not None):
        return False
    path = log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "w" if os.path.exists(path) and os.path.getsize(path) > _LOG_LIMIT_BYTES else "a"
        # The log lives as long as the program, so it cannot be a ``with`` block.
        stream = open(path, mode, encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
    except OSError:
        return False
    stream.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} KaramTC is starting\n")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    _redirect_c_streams(stream)
    return True
