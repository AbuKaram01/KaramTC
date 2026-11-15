# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""OCR of a single page that tolerates failures belonging to that page alone."""

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
    """The outcome of OCR on one page: exactly one of the two fields is set.

    Attributes:
        result: The OCR result, if OCR succeeded.
        failure: The reason why this page failed, otherwise.
    """

    result: OcrResult | None
    failure: str | None


def page_failure_text(page_number: int, reason: str) -> str:
    """Return the text that goes into the text output in place of a page that could not be read.

    It is one distinctive line, so that such pages are easy to search for ("⚠ Page") and to find again
    programmatically.
    """
    return f"[\u26a0 Page {page_number} could not be read: {reason}]"


def lighter_retry_dpi(dpi: int) -> int | None:
    """Return the resolution for the one retry of a failed page: a clearly lighter render.

    Returns None if *dpi* is already as low as a retry is allowed to go.
    """
    low, high = RETRY_DPI_RANGE
    target = max(low, min(high, int(dpi * RETRY_DPI_FACTOR)))
    return target if target < dpi else None


class PageOcrRunner:
    """OCR of single pages with page-level failure handling.

    A failure that belongs to one page (OcrPageError) is retried once from a lighter re-render and then reported
    in the outcome. A Stop request raises CancelledError. Every failure that is NOT about the page (missing
    language data, Tesseract not installed and so on) propagates to the caller and ends the job, because
    continuing would only repeat it on every remaining page.

    Args:
        renderer: Renders the lighter image for the retry.
        provider: Identifier of the OCR provider.
        lang: The OCR language.
        options: The OCR engine options.
        cancel_event: When set, the page in progress is abandoned with CancelledError.
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
        """Run OCR on one page and return its outcome.

        Args:
            page_index: Zero-based index of the page.
            image_path: The rendered page image, or None if rendering failed.
            render_error: Why rendering failed, used as the failure reason when there is no image.
            on_message: Receives status messages from the OCR engine and about the retry.

        Raises:
            CancelledError: The cancel event was set while the page was processed.
        """
        if not image_path or not os.path.exists(image_path):
            return PageOcrOutcome(None, render_error or "the page image could not be created")
        try:
            return PageOcrOutcome(self._attempt(image_path, on_message), None)
        except OcrPageError as error:
            reason = short_reason(error)
        return self._retry_at_lower_resolution(page_index, reason, on_message)

    def _attempt(self, image_path: str, on_message) -> OcrResult:
        """Run OCR on one image, converting any error caused by a Stop request into CancelledError."""
        try:
            return run_ocr(
                image_path, self._provider, self._lang,
                progress_cb=on_message, cancel_event=self._cancel_event, options=self._options,
            )
        except Exception:
            # If Stop was pressed while OCR was running on this page, report it as a cancellation (which leaves
            # the job resumable) and not as an error.
            if self._cancel_event.is_set():
                raise CancelledError()
            raise

    def _retry_at_lower_resolution(self, page_index: int, reason: str, on_message) -> PageOcrOutcome:
        """Re-render the page at a lower resolution and try OCR once more.

        Args:
            page_index: Zero-based index of the page.
            reason: Why the first attempt failed. It is the failure reason if no retry is possible.
            on_message: Receives a status message about the retry.
        """
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
