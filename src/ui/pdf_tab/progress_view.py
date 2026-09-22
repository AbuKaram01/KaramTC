# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/pdf_tab/progress_view.py — The progress card shown while a book is extracted.
"""
from __future__ import annotations

from core.book import events
from ui.progress_frame import ProgressFrame


class ProgressCard(ProgressFrame):
    """Renders the pipeline's progress events (see core/book/events.py)."""

    def __init__(self, on_stop):
        super().__init__(on_stop)
        self._skipped_pages = 0
        self._handlers = {
            events.STAGE: self._on_stage,
            events.CLASSIFY: self._on_classify,
            events.CONVERT: self._on_convert,
            events.DIRECT: self._on_direct,
            events.OCR: self._on_ocr,
            events.KEY: self._on_key,
            events.PAGE_FAILED: self._on_page_failed,
        }

    def start(self, pdf_name: str) -> None:
        self._skipped_pages = 0
        self.reset(f"Preparing — {pdf_name}")

    def update(self, kind: str, *args) -> None:
        handler = self._handlers.get(kind)
        if handler:
            handler(*args)

    # ── Event handlers ────────────────────────────────────────────────

    def _skipped_suffix(self) -> str:
        return f" \u2022 {self._skipped_pages} skipped" if self._skipped_pages else ""

    def _on_stage(self, label, *_):
        self._title.set_text(label)
        self._detail.set_text("")

    def _on_classify(self, page, total):
        self._set_progress(page / total if total else 0, f"Analysing page {page} of {total}")
        self._title.set_text("Analysing PDF pages…")
        self._detail.set_text("")

    def _on_convert(self, done, total):
        self._set_progress(done / total if total else 0, f"Image {done} of {total}")
        self._title.set_text("Converting pages to images…")
        self._detail.set_text("")

    def _on_direct(self, position, total):
        self._set_progress(
            position / total if total else 0, f"Page {position} of {total}{self._skipped_suffix()}",
        )
        self._detail.set_text("Native text — extracted directly")

    def _on_ocr(self, position, total):
        self._set_progress(
            (position - 1) / total if total else 0, f"Page {position} of {total}{self._skipped_suffix()}",
        )
        self._detail.set_text("Running OCR…")

    def _on_key(self, message, *_):
        self._detail.set_text(message)

    def _on_page_failed(self, page_number, _reason, failed_so_far):
        self._skipped_pages = failed_so_far
        self._detail.set_text(f"Page {page_number} couldn\u2019t be read \u2014 skipped, continuing")
