# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The plain-text output file, written crash-safely.

Every page is flushed and synced to disk before the progress record notes it. After a crash the file may therefore
hold one page more than the progress says. The size saved in the progress record lets a resume cut that tail off.
"""

from __future__ import annotations

import os


class TextOutput:
    """Appends extracted pages to the .txt file.

    Args:
        path: The .txt file.
        append: Continue the existing file (a resumed job) instead of starting a new one.
    """

    def __init__(self, path: str, append: bool):
        self._file = open(path, "ab" if append else "wb")  # noqa: SIM115 — closed by close()

    def size(self) -> int | None:
        """Return the current size of the file in bytes."""
        return self._file.tell()

    def write_page(self, page_number: int, text: str, with_page_marker: bool) -> int | None:
        """Append one page, flush it to disk and return the file size afterwards.

        Args:
            page_number: The 1-based page number of the original book.
            text: The text of the page.
            with_page_marker: Precede the text with a "----- Page N -----" line.
        """
        chunk = f"\n\n----- Page {page_number} -----\n\n" if with_page_marker else ""
        chunk += (text or "").strip() + "\n"
        self._file.write(chunk.encode("utf-8"))
        self._file.flush()
        os.fsync(self._file.fileno())
        return self._file.tell()

    def truncate_to(self, size: int | None) -> None:
        """Cut the file back to *size* bytes; None leaves it unchanged."""
        if size is None:
            return
        self._file.flush()
        self._file.truncate(size)
        self._file.seek(size)
        os.fsync(self._file.fileno())

    def close(self) -> None:
        """Close the file."""
        self._file.close()


class NoTextOutput:
    """Stands in for TextOutput when no .txt file is wanted (PDF-only output).

    It has the interface of TextOutput, and every method does nothing and reports no file size.
    """

    def size(self) -> int | None:
        """Return None: there is no file."""
        return None

    def write_page(self, page_number: int, text: str, with_page_marker: bool) -> int | None:
        """Discard the page and return None."""
        return None

    def truncate_to(self, size: int | None) -> None:
        """Do nothing."""
        pass

    def close(self) -> None:
        """Do nothing."""
        pass


def text_file_matches_progress(path: str, recorded_size: int | None) -> bool:
    """Reconcile an existing .txt file with the size the progress record says it had after the last recorded page.

    Returns False if the file is missing or shorter than recorded. The text of the "already completed" pages no
    longer exists then, so the job must restart from the first page instead of silently leaving them out. A longer
    file (a page was written but not yet recorded when a crash hit) is cut back to the recorded size, so that a
    plain append cannot write that page twice.
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
