# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/text_output.py — The plain-text output file, written crash-safely.

Every page is flushed and fsynced before progress records it. After a crash
the file may therefore hold one page more than the progress says; the size
saved in the progress record lets a resume cut that tail off.
"""
from __future__ import annotations

import os


class TextOutput:
    """Appends extracted pages to the .txt file."""

    def __init__(self, path: str, append: bool):
        self._file = open(path, "ab" if append else "wb")  # noqa: SIM115 — closed by close()

    def size(self) -> int | None:
        return self._file.tell()

    def write_page(self, page_number: int, text: str, with_page_marker: bool) -> int | None:
        """Appends one page; returns the file size afterwards."""
        chunk = f"\n\n----- Page {page_number} -----\n\n" if with_page_marker else ""
        chunk += (text or "").strip() + "\n"
        self._file.write(chunk.encode("utf-8"))
        self._file.flush()
        os.fsync(self._file.fileno())
        return self._file.tell()

    def truncate_to(self, size: int | None) -> None:
        if size is None:
            return
        self._file.flush()
        self._file.truncate(size)
        self._file.seek(size)
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()


class NoTextOutput:
    """Stands in for TextOutput when no .txt file is wanted (PDF-only output)."""

    def size(self) -> int | None:
        return None

    def write_page(self, page_number: int, text: str, with_page_marker: bool) -> int | None:
        return None

    def truncate_to(self, size: int | None) -> None:
        pass

    def close(self) -> None:
        pass


def text_file_matches_progress(path: str, recorded_size: int | None) -> bool:
    """
    Reconciles an existing .txt file with the size the progress record says it
    had after the last fully recorded page.

    Returns False if the file is missing or shorter than recorded — the text of
    the "already completed" pages no longer exists, so the job must restart
    from page 1 rather than silently leave them out. A longer file (a page
    written but not yet recorded when a crash hit) is cut back to the recorded
    size, so a plain append can't write that page twice.
    """
    if not os.path.exists(path):
        return False
    actual = os.path.getsize(path)
    if recorded_size is None or actual == recorded_size:
        return True
    if actual < recorded_size:
        return False
    with open(path, "r+b") as text_file:
        text_file.truncate(recorded_size)
    return True
