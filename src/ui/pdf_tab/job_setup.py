# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Turn the state of the PDF tab into a job to run.

Plain functions, no widgets: what blocks a start, which output files a new run would overwrite, whether the output
folder is usable, and the BookRequest.
"""

from __future__ import annotations

import contextlib
import os

import settings as app_settings
from config import BOOK_IMAGE_DPI, BOOK_IMAGE_JPEG_QUALITY, PROVIDER_TESSERACT
from core.book import (
    IMAGE_MODE_OFF, OUTPUT_BOTH, OUTPUT_PDF, OUTPUT_TXT, BookJobSettings, BookRequest,
    book_paths, normalize_image_dpi, normalize_jpeg_quality,
)
from providers.tesseract import DEFAULT_LANG, is_installed
from ui import saved_settings


def problem_blocking_start(
    image_mode: str, has_languages: bool, page_count: int | None, excluded_count: int,
) -> str | None:
    """Return why extraction cannot start right now (a message for the user), or None."""
    # "Off" extracts native text only, so it needs neither Tesseract nor a language.
    if image_mode != IMAGE_MODE_OFF:
        if not is_installed():
            return "Tesseract is not installed — please install it first"
        if not has_languages:
            return "No OCR language available \u2014 pick one from the gear icon (OCR Settings)"
    if page_count and excluded_count >= page_count:
        return "All pages are excluded \u2014 include at least one page to extract"
    return None


def existing_outputs(pdf_path: str, output_dir: str | None, output_format: str) -> list[str]:
    """Return the names of the files in the output folder that a fresh extraction would overwrite."""
    folder = output_dir or os.path.dirname(os.path.abspath(pdf_path))
    paths = book_paths(pdf_path, folder)
    candidates = []
    if output_format in (OUTPUT_TXT, OUTPUT_BOTH):
        candidates.append(paths.txt_path)
    if output_format in (OUTPUT_PDF, OUTPUT_BOTH):
        candidates.append(paths.pdf_path)
    return [os.path.basename(path) for path in candidates if os.path.exists(path)]


def output_folder_is_usable(folder: str) -> bool:
    """Create *folder* if needed and return True if files can be written into it."""
    with contextlib.suppress(OSError):
        os.makedirs(folder, exist_ok=True)
    return os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK)


def build_request(
    pdf_path: str, output_dir: str, language: str | None, options, excluded_pages: set[int],
) -> BookRequest:
    """Snapshot everything the worker needs into a BookRequest.

    The worker must keep processing this exact file with these settings even if the UI changes meanwhile.

    Args:
        pdf_path: The PDF to extract.
        output_dir: The folder that receives the output files.
        language: The OCR language code, or None for the default language.
        options: The BookOptions of the PDF tab (output format, page numbers, ...).
        excluded_pages: The pages the user excluded; copied, so that later UI changes do not affect the job.
    """
    settings = BookJobSettings(
        lang=language or DEFAULT_LANG,
        page_numbers=options.page_numbers,
        enhance_contrast=options.enhance_contrast,
        image_mode=options.image_mode,
        dpi=normalize_image_dpi(app_settings.get(saved_settings.PDF_IMAGE_DPI, BOOK_IMAGE_DPI)),
        jpg_quality=normalize_jpeg_quality(
            app_settings.get(saved_settings.PDF_JPEG_QUALITY, BOOK_IMAGE_JPEG_QUALITY)),
        output_format=options.output_format,
        engine=saved_settings.read_engine_settings(),
        excluded_pages=set(excluded_pages),
        cpu_threads=saved_settings.cpu_threads_setting(),
    )
    return BookRequest(pdf_path, PROVIDER_TESSERACT, book_paths(pdf_path, output_dir), settings)
