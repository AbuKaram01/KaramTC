# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/progress.py — Saved progress of an interrupted extraction.

The progress file is what makes Stop and Resume possible. It may be damaged,
hand-edited or written by an older version, so it is validated before use: a
bad file must never be able to crash a resume.
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
    """True if *data* has the shape the extraction pipeline relies on."""
    return isinstance(data, dict) and all(check(data) for check in _FIELD_CHECKS)


class BookProgress:
    """Persists extraction progress to disk; enables resuming interrupted extractions."""

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}

    def load(self) -> bool:
        """Loads the saved progress; False (and empty data) if there is none or
        the file isn't a usable progress record."""
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
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as temporary_file:
            json.dump(self.data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary, self.path)

    def delete(self) -> None:
        with contextlib.suppress(OSError):
            os.remove(self.path)

    def is_resumable_for(self, pdf_path: str) -> bool:
        return (
            self.data.get("status") == STATUS_IN_PROGRESS
            and self.data.get("pdf_path") == pdf_path
        )

    def pdf_was_replaced(self, pdf_path: str) -> bool:
        """True if the PDF no longer has the size/mtime it had when the job was
        saved — resuming would silently mix pages from two different documents."""
        saved = self.data.get("pdf_fingerprint")
        current = pdf_fingerprint(pdf_path)
        return saved is not None and current is not None and list(saved) != list(current)


@dataclass
class SavedJob:
    progress: BookProgress
    output_dir: str | None      # the folder that was searched (None = next to the PDF)


def _load_saved_job(pdf_path: str, output_dir: str | None) -> SavedJob | None:
    progress = BookProgress(book_paths(pdf_path, output_dir).progress_path)
    if progress.load() and progress.is_resumable_for(pdf_path):
        return SavedJob(progress, output_dir)
    return None


def find_saved_job(pdf_path: str, output_dir: str | None, also_search_pdf_folder: bool = False) -> SavedJob | None:
    """
    The interrupted job for *pdf_path* saved in *output_dir*, if any.

    *also_search_pdf_folder* is for when a book has just been opened: a job
    interrupted before an output folder was being remembered (or while a
    different one was) lives next to the PDF, so look there too rather than
    silently starting a second job.
    """
    job = _load_saved_job(pdf_path, output_dir)
    if job is None and also_search_pdf_folder:
        pdf_folder = os.path.dirname(os.path.abspath(pdf_path))
        if pdf_folder != output_dir:
            job = _load_saved_job(pdf_path, pdf_folder)
    return job
