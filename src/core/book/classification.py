# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/classification.py — Native text or scanned image? Decided per page.
"""
from __future__ import annotations

import threading
import unicodedata

from core.book import events
from core.book.constants import GARBLED_TEXT_MAX_RATIO, PAGE_IMAGE, PAGE_TEXT, TEXT_PAGE_MIN_CHARS
from core.book.errors import CancelledError
from core.book.pdf_io import open_pdf, page_text

_UNUSABLE_CATEGORIES = ("Co", "Cc")     # private-use glyphs, control codes
_REPLACEMENT_CHARACTER = "\ufffd"


def native_text_looks_garbled(text: str) -> bool:
    """
    True if *text* (a page's native text layer) is mostly unusable characters:
    U+FFFD replacement characters, private-use glyphs, or control codes. That
    is what PyMuPDF returns for fonts with a missing or broken Unicode map, so
    such a page is better served by OCR than by "extracting" its text layer.
    Deliberately conservative — a few stray bullets or symbols never trip it.
    """
    visible = [char for char in text if not char.isspace()]
    if not visible:
        return False
    unusable = sum(
        1 for char in visible
        if char == _REPLACEMENT_CHARACTER or unicodedata.category(char) in _UNUSABLE_CATEGORIES
    )
    return unusable / len(visible) >= GARBLED_TEXT_MAX_RATIO


def _classify_page(doc, page_index: int) -> str:
    try:
        text = page_text(doc, page_index)
    except Exception:
        # A page whose content can't be parsed has no usable text layer: treat
        # it like a scanned page (it gets OCR'd from its image) rather than
        # letting one damaged page stop the whole analysis.
        return PAGE_IMAGE
    reliable = len(text) >= TEXT_PAGE_MIN_CHARS and not native_text_looks_garbled(text)
    return PAGE_TEXT if reliable else PAGE_IMAGE


def classify_pages(
    pdf_path: str,
    progress_cb=None,
    cancel_event: threading.Event | None = None,
) -> list[str]:
    """
    Analyses every page and returns PAGE_TEXT or PAGE_IMAGE for each.
      PAGE_TEXT  → reliable selectable native text; extracted directly via PyMuPDF.
      PAGE_IMAGE → scanned, too little text, or a garbled text layer; needs
                   image conversion + OCR.
    """
    doc = open_pdf(pdf_path)
    try:
        total = doc.page_count
        page_types = []
        for index in range(total):
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()
            if progress_cb:
                progress_cb(events.CLASSIFY, index + 1, total)
            page_types.append(_classify_page(doc, index))
        return page_types
    finally:
        doc.close()
