# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Saved progress of an interrupted extraction.

The progress file is what makes Stop and Resume possible. It may be damaged, hand-edited or written by an older
version, so it is validated before use: a bad file must never be able to crash a resume.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass

from core.book.constants import PAGE_IMAGE, PAGE_TEXT
from core.book.paths import book_paths
from core.book.pdf_io import pdf_fingerprint

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"


def _is_plain_int(value) -> bool:
    """Return True for an int that is not a bool (bool is a subclass of int in Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _has_status_and_pdf_path(data: dict) -> bool:
    return isinstance(data.get("status"), str) and isinstance(data.get("pdf_path"), str)


def _has_valid_completed_pages(data: dict) -> bool:
    done = data.get("completed_pages", 0)
    return _is_plain_int(done) and done >= 0


def _has_valid_page_types(data: dict) -> bool:
    page_types = data.get("page_types")
    return page_types is None or (
        isinstance(page_types, list) and all(kind in (PAGE_TEXT, PAGE_IMAGE) for kind in page_types)
    )


def _has_valid_excluded_pages(data: dict) -> bool:
    excluded = data.get("excluded_pages", [])
    return isinstance(excluded, list) and all(isinstance(index, int) for index in excluded)


def _has_valid_fingerprint(data: dict) -> bool:
    fingerprint = data.get("pdf_fingerprint")
    return fingerprint is None or (isinstance(fingerprint, (list, tuple)) and len(fingerprint) == 2)


def _has_valid_text_size(data: dict) -> bool:
    size = data.get("txt_size")
    return size is None or (isinstance(size, int) and size >= 0)


def _has_valid_failed_pages(data: dict) -> bool:
    failed = data.get("failed_pages", {})
    return isinstance(failed, dict) and all(
        str(page).isdigit() and isinstance(reason, str) for page, reason in failed.items()
    )


# A progress record is usable only if every one of these checks passes.
_FIELD_CHECKS = (
    _has_status_and_pdf_path,
    _has_valid_completed_pages,
    _has_valid_page_types,
    _has_valid_excluded_pages,
    _has_valid_fingerprint,
    _has_valid_text_size,
    _has_valid_failed_pages,
)


def progress_is_sane(data) -> bool:
    """Return True if *data* has the shape that the extraction pipeline relies on."""
    return isinstance(data, dict) and all(check(data) for check in _FIELD_CHECKS)


class BookProgress:
    """The progress record of one extraction, persisted to disk so that an interrupted extraction can be resumed.

    Args:
        path: The progress file.

    Attributes:
        path: The progress file.
        data: The progress record. It is empty until load() succeeds or the pipeline fills it in.
    """

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}

    def load(self) -> bool:
        """Load the saved progress.

        Returns False, leaving ``data`` empty, if there is none or the file is not a usable progress record.
        """
        self.data = {}
        if not os.path.exists(self.path):
            return False
        try:
            with open(self.path, encoding="utf-8") as progress_file:
                data = json.load(progress_file)
        except Exception:
            return False
        if not progress_is_sane(data):
            return False
        self.data = data
        return True

    def save(self) -> None:
        """Write the progress record to disk.

        The record is written to a temporary file, flushed to disk and then renamed over the progress file, so
        that a crash never leaves a half-written progress file behind.
        """
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as temporary_file:
            json.dump(self.data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary, self.path)

    def delete(self) -> None:
        """Remove the progress file. A missing or undeletable file is ignored."""
        with contextlib.suppress(OSError):
            os.remove(self.path)

    def is_resumable_for(self, pdf_path: str) -> bool:
        """Return True if the loaded record is an unfinished job for *pdf_path*."""
        return (
            self.data.get("status") == STATUS_IN_PROGRESS
            and self.data.get("pdf_path") == pdf_path
        )

    def pdf_was_replaced(self, pdf_path: str) -> bool:
        """Return True if the PDF no longer has the size and modification time it had when the job was saved.

        Resuming in that case would silently mix pages from two different documents.
        """
        saved = self.data.get("pdf_fingerprint")
        current = pdf_fingerprint(pdf_path)
        return saved is not None and current is not None and list(saved) != list(current)


@dataclass
class SavedJob:
    """An interrupted job found on disk, together with the folder it was found in."""

    progress: BookProgress
    # The folder that was searched. None means the folder of the PDF.
    output_dir: str | None


def _load_saved_job(pdf_path: str, output_dir: str | None) -> SavedJob | None:
    """Return the resumable job for *pdf_path* in *output_dir*, or None."""
    progress = BookProgress(book_paths(pdf_path, output_dir).progress_path)
    if progress.load() and progress.is_resumable_for(pdf_path):
        return SavedJob(progress, output_dir)
    return None


def find_saved_job(pdf_path: str, output_dir: str | None, also_search_pdf_folder: bool = False) -> SavedJob | None:
    """Return the interrupted job for *pdf_path* saved in *output_dir*, or None if there is none.

    Set *also_search_pdf_folder* when a book has just been opened. A job that was interrupted before an output
    folder was being remembered, or while a different one was, lives next to the PDF. Looking there too avoids
    silently starting a second job.
    """
    job = _load_saved_job(pdf_path, output_dir)
    if job is None and also_search_pdf_folder:
        pdf_folder = os.path.dirname(os.path.abspath(pdf_path))
        if pdf_folder != output_dir:
            job = _load_saved_job(pdf_path, pdf_folder)
    return job
