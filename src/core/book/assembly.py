# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Assembly of the final searchable PDF from the source pages and the OCR output."""

from __future__ import annotations

import os

from core.book.constants import A4_PAGE_SIZE_POINTS, PAGE_TEXT
from core.book.paths import BookPaths
from core.book.pdf_io import open_pdf, require_fitz
from core.book.workdir import page_fragment_path, page_image_path


def _insert_page_from_file(combined, path: str) -> bool:
    """Append the single page stored in *path* (a PDF fragment or an image) to *combined*.

    Returns False if the file is missing or cannot be read.
    """
    if not os.path.exists(path):
        return False
    fitz = require_fitz()
    try:
        part = fitz.open(path)
        try:
            combined.insert_pdf(part)
        finally:
            part.close()
        return True
    except Exception:
        return False


def _insert_best_available_page(combined, source, paths: BookPaths, page_index: int) -> None:
    """Add the best available version of an OCR'd page to *combined*.

    The sources are tried in order of preference: the single-page PDF fragment that Tesseract produced (image plus
    invisible text layer), the plain scanned image, the page as it is in the source and, only if even that is
    unreadable, an empty page so that the page numbering still lines up. A damaged fragment or image must neither
    abort an assembly that has taken hours to get here nor silently drop the page.
    """
    if _insert_page_from_file(combined, page_fragment_path(paths.images_dir, page_index)):
        return
    if _insert_page_from_file(combined, page_image_path(paths.images_dir, page_index)):
        return
    try:
        combined.insert_pdf(source, from_page=page_index, to_page=page_index)
    except Exception:
        combined.new_page(width=A4_PAGE_SIZE_POINTS[0], height=A4_PAGE_SIZE_POINTS[1])


def assemble_pdf(
    pdf_path: str,
    paths: BookPaths,
    page_types: list[str],
    page_indices: list[int],
    failed_indices: set[int] | None = None,
) -> None:
    """Build the searchable PDF at ``paths.pdf_path`` by walking *page_indices* in order.

    Only the pages that were actually extracted are included, so excluded pages leave gaps. Each page comes from
    one of three places:

    * Text pages are copied straight from the source PDF, because they already have a real native text layer.
    * OCR'd pages come from the fragment that Tesseract produced for that page.
    * Pages in *failed_indices* (OCR gave up on them) are copied from the source as they are, untouched and
      without a text layer. This is better than a re-rendered image.

    Args:
        pdf_path: The source PDF.
        paths: The output and working locations of the job.
        page_types: PAGE_TEXT or PAGE_IMAGE for every page of the source, indexed by page.
        page_indices: Zero-based indices of the pages to include, in output order.
        failed_indices: Zero-based indices of the pages for which OCR failed.
    """
    fitz = require_fitz()
    failed_indices = failed_indices or set()
    combined = fitz.open()
    source = open_pdf(pdf_path)
    try:
        for index in page_indices:
            if page_types[index] == PAGE_TEXT or index in failed_indices:
                combined.insert_pdf(source, from_page=index, to_page=index)
            else:
                _insert_best_available_page(combined, source, paths, index)
        combined.save(paths.pdf_path)
    finally:
        combined.close()
        source.close()
