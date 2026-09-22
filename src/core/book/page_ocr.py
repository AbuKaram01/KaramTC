# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/page_ocr.py — OCR of one page that tolerates failures belonging to that page alone.
"""
from __future__ import annotations

import os
import threading
from typing import NamedTuple

from core.book.constants import RETRY_DPI_FACTOR, RETRY_DPI_RANGE
from core.book.errors import CancelledError
from core.book.rendering import PageImageRenderer, short_reason
from providers.ocr_types import OcrOptions, OcrPageError, OcrResult
from providers.registry import run_ocr


class PageOcrOutcome(NamedTuple):
    """Exactly one of the two is set: the OCR result, or why this page failed."""
    result: OcrResult | None
    failure: str | None


def page_failure_text(page_number: int, reason: str) -> str:
    """What goes into the text output in place of a page that couldn't be read.
    One distinctive line, so the pages are easy to search for ("⚠ Page") and
    to find again programmatically."""
    return f"[\u26a0 Page {page_number} could not be read: {reason}]"


def lighter_retry_dpi(dpi: int) -> int | None:
    """Resolution for the one retry of a failed page: a clearly lighter render,
    or None if *dpi* is already as low as a retry is allowed to go."""
    low, high = RETRY_DPI_RANGE
    target = max(low, min(high, int(dpi * RETRY_DPI_FACTOR)))
    return target if target < dpi else None


class PageOcrRunner:
    """
    OCRs single pages. A failure that belongs to one page is retried once from
    a lighter re-render and then reported; Stop requests raise CancelledError,
    and so does every failure that is NOT about the page (missing language
    data, Tesseract not installed, …): continuing would only repeat it on
    every remaining page.
    """

    def __init__(
        self,
        renderer: PageImageRenderer,
        provider: str,
        lang: str,
        options: OcrOptions,
        cancel_event: threading.Event,
    ):
        self._renderer = renderer
        self._provider = provider
        self._lang = lang
        self._options = options
        self._cancel_event = cancel_event

    def run(self, page_index: int, image_path: str | None, render_error: str | None, on_message=None) -> PageOcrOutcome:
        if not image_path or not os.path.exists(image_path):
            return PageOcrOutcome(None, render_error or "the page image could not be created")
        try:
            return PageOcrOutcome(self._attempt(image_path, on_message), None)
        except OcrPageError as error:
            reason = short_reason(error)
        return self._retry_at_lower_resolution(page_index, reason, on_message)

    def _attempt(self, image_path: str, on_message) -> OcrResult:
        try:
            return run_ocr(
                image_path, self._provider, self._lang,
                progress_cb=on_message, cancel_event=self._cancel_event, options=self._options,
            )
        except Exception:
            # If Stop was pressed while OCR was running on this page, surface
            # it as a cancellation (→ resumable) rather than as an error.
            if self._cancel_event.is_set():
                raise CancelledError()
            raise

    def _retry_at_lower_resolution(self, page_index: int, reason: str, on_message) -> PageOcrOutcome:
        retry_dpi = lighter_retry_dpi(self._renderer.settings.dpi)
        if retry_dpi is None:
            return PageOcrOutcome(None, reason)
        if on_message:
            on_message(f"Page {page_index + 1} failed — retrying at {retry_dpi} DPI…")

        rendered = self._renderer.at_dpi(retry_dpi).render([page_index], failures={})
        light_image = rendered.get(page_index)
        if not light_image:
            return PageOcrOutcome(None, reason)
        try:
            return PageOcrOutcome(self._attempt(light_image, on_message), None)
        except OcrPageError as error:
            again = short_reason(error)
            if again == reason:
                return PageOcrOutcome(None, f"{reason} (a retry at {retry_dpi} DPI failed too)")
            return PageOcrOutcome(None, f"{reason}; retry at {retry_dpi} DPI: {again}")
