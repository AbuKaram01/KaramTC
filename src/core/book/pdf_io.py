# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/pdf_io.py — Opening PDFs and reading their basic properties.
"""
from __future__ import annotations

import os


def require_fitz():
    """The PyMuPDF module, or a friendly RuntimeError if it isn't installed."""
    try:
        from core.pdf_backend import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF is not installed.\nRun: pip install pymupdf")
    return fitz


def open_pdf(pdf_path: str):
    """
    Opens a PDF with PyMuPDF, raising a friendly RuntimeError for the common
    failure modes instead of letting a cryptic PyMuPDF exception (or a silently
    wrong empty-text classification) propagate up to the UI.
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
    """
    (size, mtime) of a PDF file, or None if it can't be stat'd.

    Detects whether a file at a saved-progress path has since been replaced by
    different content, so a resume never runs against the wrong file.
    """
    try:
        stat = os.stat(pdf_path)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime)


def pdf_page_count(pdf_path: str) -> int:
    doc = open_pdf(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def page_text(doc, page_index: int) -> str:
    """The native text of one page of an already-open document."""
    return doc.load_page(page_index).get_text("text").strip()


def extract_text_direct(pdf_path: str, page_index: int, doc=None) -> str:
    """
    Native selectable text of a single PDF page.

    Pass an already-open *doc* when extracting many pages: opening the PDF
    again for every page re-parses it each time, which measured ~12x slower
    on a 1500-page book (and grows with the size of the file).
    """
    if doc is not None:
        return page_text(doc, page_index)
    doc = open_pdf(pdf_path)
    try:
        return page_text(doc, page_index)
    finally:
        doc.close()
