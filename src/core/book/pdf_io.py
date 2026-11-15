# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Opening PDFs and reading their basic properties."""

from __future__ import annotations

import os


def require_fitz():
    """Return the PyMuPDF module.

    Raises:
        RuntimeError: PyMuPDF is not installed. The message tells the user how to install it.
    """
    try:
        from core.pdf_backend import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF is not installed.\nRun: pip install pymupdf")
    return fitz


def open_pdf(pdf_path: str):
    """Open a PDF with PyMuPDF and return the document.

    The common failure modes are reported as a RuntimeError with a readable message. Otherwise a cryptic PyMuPDF
    exception, or a silently wrong empty-text classification, would propagate up to the UI.

    Raises:
        RuntimeError: PyMuPDF is missing, the file cannot be opened or the PDF is password-protected.
    """
    fitz = require_fitz()
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise RuntimeError(f"Could not open PDF: {exc}") from exc
    if doc.needs_pass:
        doc.close()
        raise RuntimeError("This PDF is password-protected — remove the password and try again")
    return doc


def pdf_fingerprint(pdf_path: str) -> tuple[int, float] | None:
    """Return the (size, mtime) of a PDF file, or None if the file cannot be examined.

    The fingerprint detects whether the file at a saved-progress path has since been replaced by different
    content, so that a resume never runs against the wrong file.
    """
    try:
        stat = os.stat(pdf_path)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime)


def pdf_page_count(pdf_path: str) -> int:
    """Return the number of pages of the PDF."""
    doc = open_pdf(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def page_text(doc, page_index: int) -> str:
    """Return the native text of one page of an already-open document, stripped of surrounding whitespace."""
    return doc.load_page(page_index).get_text("text").strip()


def extract_text_direct(pdf_path: str, page_index: int, doc=None) -> str:
    """Return the native, selectable text of a single PDF page.

    Pass an already-open *doc* when extracting many pages. Opening the PDF again for every page re-parses it each
    time, which was measured at about 12 times slower on a 1500-page book and grows with the size of the file.
    """
    if doc is not None:
        return page_text(doc, page_index)
    doc = open_pdf(pdf_path)
    try:
        return page_text(doc, page_index)
    finally:
        doc.close()
