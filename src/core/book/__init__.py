# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book — PDF book text extraction (hybrid: native text + OCR).

Typical use:
    request = BookRequest(pdf_path, "tesseract", book_paths(pdf_path, out_dir), BookJobSettings(lang="eng"))
    result = run_book_extraction(request, progress_cb, cancel_event)

No GTK dependency — can be tested independently.
"""
from core.book import events
from core.book.classification import classify_pages, native_text_looks_garbled
from core.book.constants import (
    IMAGE_MODE_AUTO, IMAGE_MODE_OFF, IMAGE_MODE_ON, IMAGE_MODES,
    OUTPUT_BOTH, OUTPUT_PDF, OUTPUT_TXT,
)
from core.book.errors import CancelledError
from core.book.extraction import run_book_extraction
from core.book.job import BookJobSettings, BookRequest, BookResult
from core.book.normalize import normalize_image_dpi, normalize_image_mode, normalize_jpeg_quality
from core.book.paths import BookPaths, book_paths
from core.book.pdf_io import extract_text_direct, pdf_fingerprint, pdf_page_count
from core.book.progress import BookProgress, SavedJob, find_saved_job

__all__ = [
    "BookJobSettings", "BookPaths", "BookProgress", "BookRequest", "BookResult", "CancelledError",
    "IMAGE_MODES", "IMAGE_MODE_AUTO", "IMAGE_MODE_OFF", "IMAGE_MODE_ON",
    "OUTPUT_BOTH", "OUTPUT_PDF", "OUTPUT_TXT", "SavedJob",
    "book_paths", "classify_pages", "events", "extract_text_direct", "find_saved_job",
    "native_text_looks_garbled", "normalize_image_dpi", "normalize_image_mode",
    "normalize_jpeg_quality", "pdf_fingerprint", "pdf_page_count", "run_book_extraction",
]
