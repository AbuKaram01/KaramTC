# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/ascii_paths.py — Keeps non-ASCII paths away from tesseract.exe on Windows.

Tesseract's Windows builds are ANSI programs: the paths on their command line, and the folder
they are started from, reach them converted to the system's ANSI code page. Arabic letters
survive that only on a system whose code page has them (1256); on any other they become "?",
and a user name in Arabic (so a TEMP folder and a language-data folder in Arabic) then makes
Tesseract fail with "did not produce any output file" or "could not load language data".

Python itself has no such problem, so the answer is to let Tesseract see ASCII only:

* it is started *inside* the temporary working folder, and is given file names relative to it
  ("result", "input.png"); the working folder is handed to Windows as UTF-16, never through
  Tesseract's command line, so it can hold any letters;
* a picture elsewhere with a non-ASCII path is copied into that folder first;
* the program and the language-data folder get their 8.3 short names, or, for language data
  when the volume has none, a directory junction inside the working folder.

Everything here does nothing outside Windows, and nothing for paths that are already ASCII.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

_CREATE_NO_WINDOW = 0x08000000
_JUNCTION_NAME = "tessdata"


def _on_windows() -> bool:
    return sys.platform == "win32"


def is_ascii(path: str | None) -> bool:
    return path is None or path.isascii()


def short_path(path: str) -> str | None:
    """The 8.3 form of the existing *path* if it is pure ASCII, else None (also off Windows, or when the
    volume keeps no short names: Windows then returns the long name, which is no use here)."""
    if not _on_windows():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        get_short_path_name = ctypes.windll.kernel32.GetShortPathNameW
        get_short_path_name.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_short_path_name.restype = wintypes.DWORD
        size = get_short_path_name(path, None, 0)
        if size == 0:
            return None
        buffer = ctypes.create_unicode_buffer(size)
        length = get_short_path_name(path, buffer, size)
        if length == 0 or length >= size:
            return None
    except (AttributeError, OSError, ValueError):
        return None
    return buffer.value if is_ascii(buffer.value) else None


def launchable(program_path: str) -> str:
    """*program_path* in a form Windows can start while Tesseract still sees only ASCII (its own folder is
    found from this path): the short name when the path has non-ASCII letters, else the path itself."""
    if is_ascii(program_path):
        return program_path
    return short_path(program_path) or program_path


def make_junction(target: str, link: str) -> bool:
    """Makes the folder *link* a directory junction to *target* (needs no administrator rights, unlike a
    symbolic link). False if that is not possible."""
    if not _on_windows():
        return False
    try:
        import _winapi

        _winapi.CreateJunction(target, link)
        return True
    except (ImportError, AttributeError, OSError):
        pass
    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True, check=False, timeout=20, creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and os.path.isdir(link)


@dataclass
class SafeArguments:
    """What to give Tesseract in place of the real paths, and where to start it."""
    image: str
    output_base: str
    tessdata_dir: str | None
    cwd: str | None = None          # None: start it where the application is, as usual


def _stage_image(image_path: str, work_dir: str) -> str:
    """The picture as a file name inside *work_dir* (relative to it), copying it there unless it already is."""
    in_work_dir = os.path.normcase(os.path.dirname(image_path)) == os.path.normcase(work_dir)
    if in_work_dir and is_ascii(os.path.basename(image_path)):
        return os.path.basename(image_path)
    extension = os.path.splitext(image_path)[1].lower()
    name = "input" + (extension if is_ascii(extension) else "")      # Leptonica reads the format from the content.
    try:
        shutil.copyfile(image_path, os.path.join(work_dir, name))
    except OSError:
        return image_path           # Tesseract then reports what it cannot open, as it always did.
    return name


@contextlib.contextmanager
def safe_arguments(image_path: str, output_base: str, tessdata_dir: str | None, work_dir: str):
    """
    Yields the SafeArguments to use for one Tesseract run whose files are in *work_dir* (a temporary folder
    that already exists, holding *output_base*'s files and possibly the picture).

    Unchanged, with no working folder, when nothing is non-ASCII or this is not Windows.
    """
    arguments = SafeArguments(image_path, output_base, tessdata_dir)
    if not _on_windows() or all(is_ascii(path) for path in (image_path, output_base, tessdata_dir)):
        yield arguments
        return

    arguments.cwd = work_dir
    junctions: list[str] = []
    try:
        # The output files are made inside the working folder: a name relative to it needs no ASCII path.
        arguments.output_base = os.path.basename(output_base)
        if not is_ascii(image_path):
            arguments.image = _stage_image(image_path, work_dir)
        if not is_ascii(tessdata_dir):
            arguments.tessdata_dir = short_path(tessdata_dir) or _junction_to(tessdata_dir, work_dir, junctions)
        yield arguments
    finally:
        for link in junctions:
            _remove_link(link)


def _remove_link(link: str) -> None:
    """Removes the junction *link* only, never what it points to (rmdir does that for a junction; unlink is the
    fallback for any other kind of link)."""
    try:
        os.rmdir(link)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(link)


def _junction_to(tessdata_dir: str, work_dir: str, junctions: list[str]) -> str:
    link = os.path.join(work_dir, _JUNCTION_NAME)
    if make_junction(tessdata_dir, link):
        junctions.append(link)
        return _JUNCTION_NAME
    return tessdata_dir
