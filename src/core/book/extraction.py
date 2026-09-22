# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/extraction.py — The hybrid extraction pipeline (native text + OCR).

  Start/resume — continue an interrupted job, or start a clean one.
  Stage 0      — classify pages as text (native) or image (scanned/garbled).
                 Image mode "on" skips this and treats every page as an image;
                 "off" classifies only to count weak pages, then uses native
                 text for all of them.
  Stage 1      — convert image pages to compressed JPEGs, sequentially.
  Stage 2      — extract: text pages directly via PyMuPDF, image pages via OCR.
  Finalize     — assemble the searchable PDF if one was requested.

No GTK dependency — can be tested independently.
"""
from __future__ import annotations

import threading

from core.book import events
from core.book.assembly import assemble_pdf
from core.book.classification import classify_pages
from core.book.constants import (
    IMAGE_MODE_OFF, IMAGE_MODE_ON, MAX_CONSECUTIVE_PAGE_FAILURES, PAGE_IMAGE, PAGE_TEXT,
)
from core.book.errors import CancelledError
from core.book.job import (
    BookRequest, BookResult, new_progress_record, settings_from_progress,
)
from core.book.page_ocr import PageOcrRunner, page_failure_text
from core.book.pdf_io import extract_text_direct, open_pdf, pdf_fingerprint, pdf_page_count
from core.book.progress import STATUS_COMPLETED, BookProgress
from core.book.rendering import PageImageRenderer, RenderSettings, short_reason
from core.book.text_output import NoTextOutput, TextOutput, text_file_matches_progress
from core.book.workdir import (
    find_complete_page_images, page_fragment_path, remove_work_dir, write_bytes_atomically,
)


class BookExtraction:
    """One run of the pipeline; use run_book_extraction() to execute it."""

    def __init__(
        self,
        request: BookRequest,
        progress_cb,
        cancel_event: threading.Event,
        resume: bool,
    ):
        self._request = request
        self._paths = request.paths
        self._pdf_path = request.pdf_path
        self._progress_cb = progress_cb
        self._cancel_event = cancel_event
        self._resume = resume

        self._progress = BookProgress(self._paths.progress_path)
        self._data: dict = {}                       # the persisted progress record
        self._settings = request.settings           # replaced by the job's own saved settings
        self._ocr_confidences: list[float] = []
        self._page_types: list[str] = []
        self._included: list[int] = []              # original indices of the pages being extracted
        self._image_paths: dict[int, str] = {}
        self._render_failures: dict[int, str] = {}
        self._failed_pages: dict[int, str] = {}     # {1-based page number: reason}
        self._failure_streak: list[tuple[int, int | None]] = []   # (position, text size before it)
        self._text_output = NoTextOutput()
        self._native_doc = None                     # one shared handle for native-text pages
        self._renderer: PageImageRenderer | None = None
        self._page_ocr: PageOcrRunner | None = None

    # ── Orchestration ─────────────────────────────────────────────────

    def run(self) -> BookResult:
        self._start_or_resume()
        self._prepare_for_settings()
        self._decide_page_types()
        self._convert_scanned_pages()
        self._announce_extraction()
        self._extract_pages()
        self._finalize()
        return self._build_result()

    def _notify(self, kind: str, *args) -> None:
        if self._progress_cb:
            self._progress_cb(kind, *args)

    # ── Start / resume ────────────────────────────────────────────────

    def _start_or_resume(self) -> None:
        fingerprint = pdf_fingerprint(self._pdf_path)
        if self._resume and self._can_resume(fingerprint):
            self._data = self._progress.data
            return
        # Start clean: drop leftover page images from an earlier run of this
        # book. Existing output files are deliberately NOT deleted: the ones
        # this run produces are simply overwritten when it writes them (the
        # caller asks the user before replacing anything), and a file of the
        # *other* format — or one that merely shares the name with an
        # unrelated user file — is none of our business, and a run that fails
        # early shouldn't have destroyed the previous good result.
        remove_work_dir(self._paths.images_dir)
        self._data = new_progress_record(self._request, fingerprint)
        self._progress.data = self._data
        self._progress.save()

    def _can_resume(self, current_fingerprint) -> bool:
        if not (self._progress.load() and self._progress.is_resumable_for(self._pdf_path)):
            return False
        # Guard against resuming against a file replaced at the same path
        # since the progress was written (size/mtime changed).
        saved = self._progress.data.get("pdf_fingerprint")
        return saved is None or current_fingerprint is None or list(saved) == list(current_fingerprint)

    def _prepare_for_settings(self) -> None:
        """Adopts the settings the job started with (for resume consistency)."""
        self._settings = settings_from_progress(self._data, self._request.settings)
        self._ocr_confidences = self._data.setdefault("ocr_confidences", [])

        settings = self._settings
        options = settings.engine.to_ocr_options(
            want_pdf=settings.wants_searchable_pdf, want_confidence=True, threads=settings.cpu_threads,
        )
        self._renderer = PageImageRenderer(
            self._pdf_path, self._paths.images_dir,
            RenderSettings(settings.dpi, settings.jpg_quality, settings.enhance_contrast),
            self._cancel_event,
        )
        self._page_ocr = PageOcrRunner(
            self._renderer, self._request.provider, settings.lang, options, self._cancel_event,
        )

    # ── Stage 0: which pages are text, which are images ───────────────

    def _decide_page_types(self) -> None:
        page_types = self._data.get("page_types")
        if page_types is None:
            page_types = self._analyse_pages()
            self._data["page_types"] = page_types
            self._page_types = page_types
            self._included = self._included_indices()
            self._data["total_pages"] = len(self._included)   # pages actually being extracted
            self._progress.save()
        else:
            self._page_types = page_types
            self._included = self._included_indices()

        if not self._included:
            self._progress.delete()
            raise RuntimeError(
                "No pages selected for extraction — every page was excluded"
                if self._settings.excluded_pages else
                "This PDF appears to have no pages"
            )

    def _included_indices(self) -> list[int]:
        excluded = self._settings.excluded_pages
        return [index for index in range(len(self._page_types)) if index not in excluded]

    def _analyse_pages(self) -> list[str]:
        mode = self._settings.image_mode
        if mode == IMAGE_MODE_ON:
            # Skip analysis — convert every page to an image for OCR
            page_types = [PAGE_IMAGE] * pdf_page_count(self._pdf_path)
        else:
            self._notify(events.STAGE, "Analysing PDF pages…")
            page_types = classify_pages(
                self._pdf_path, progress_cb=self._progress_cb, cancel_event=self._cancel_event,
            )
        if mode == IMAGE_MODE_OFF:
            page_types = self._native_text_only(page_types)
        return page_types

    def _native_text_only(self, page_types: list[str]) -> list[str]:
        """
        Image mode "off": use native text for every page. The classification
        is still useful — the pages it marked as images are the ones with
        little or unreliable native text, which is what we warn about instead
        of OCR'ing.
        """
        excluded = self._settings.excluded_pages
        weak_pages = [
            index for index in range(len(page_types))
            if index not in excluded and page_types[index] == PAGE_IMAGE
        ]
        checked = len(page_types) - len(excluded)
        if checked > 0 and len(weak_pages) == checked:
            self._progress.delete()
            raise RuntimeError(
                "No usable native text was found in this PDF — it looks like a scanned book.\n"
                "Set Force image mode to Auto or On to extract it with OCR."
            )
        self._data["low_text_pages"] = len(weak_pages)
        return [PAGE_TEXT] * len(page_types)

    # ── Stage 1: convert scanned pages to images ──────────────────────

    def _scanned_indices(self) -> list[int]:
        return [index for index in self._included if self._page_types[index] == PAGE_IMAGE]

    def _convert_scanned_pages(self) -> None:
        scanned = self._scanned_indices()
        if not scanned:
            return
        images = find_complete_page_images(self._paths.images_dir)
        missing = [index for index in scanned if index not in images]
        if missing:
            self._notify(events.STAGE, f"Converting {len(missing)} page(s) to images…")
            images.update(self._renderer.render(
                missing, progress_cb=self._progress_cb, failures=self._render_failures,
            ))
        self._image_paths = images

    # ── Stage 2: extract text ─────────────────────────────────────────

    def _announce_extraction(self) -> None:
        image_count = len(self._scanned_indices())
        text_count = len(self._included) - image_count
        if self._settings.image_mode == IMAGE_MODE_ON:
            label = "Extracting text with OCR…"
        elif image_count and text_count:
            label = f"Extracting text ({text_count} native, {image_count} OCR)…"
        elif image_count:
            label = "Extracting text with OCR…"
        else:
            label = "Extracting native text…"
        self._notify(events.STAGE, label)

    def _first_page_to_extract(self) -> int:
        """
        Where to continue. If the .txt is missing or shorter than the progress
        record says (e.g. the user deleted it between runs), the text of the
        "already completed" pages no longer exists: restart from page 1
        instead of silently leaving them out of the regenerated file. (Only
        applies when a .txt is produced — a PDF-only run has no equivalent
        all-or-nothing file to lose, since each OCR page's fragment is saved
        independently.)
        """
        start = min(self._data.get("completed_pages", 0), len(self._included))
        needs_text_file = start > 0 and self._settings.wants_text
        if needs_text_file and not text_file_matches_progress(self._paths.txt_path, self._data.get("txt_size")):
            start = 0
            self._data["completed_pages"] = 0
            self._data.pop("txt_size", None)
            self._progress.save()
        return start

    def _extract_pages(self) -> None:
        start = self._first_page_to_extract()
        if self._settings.wants_text:
            self._text_output = TextOutput(self._paths.txt_path, append=start > 0)
        # Pages that could not be read are recorded (and saved with the job, so
        # a resume still reports them) and replaced by a one-line placeholder.
        self._failed_pages = {int(page): reason for page, reason in self._data.get("failed_pages", {}).items()}
        try:
            for position in range(start, len(self._included)):
                self._extract_page(position)
        finally:
            self._text_output.close()
            if self._native_doc is not None:
                self._native_doc.close()

    def _extract_page(self, position: int) -> None:
        index = self._included[position]
        if self._cancel_event.is_set():
            raise CancelledError()

        size_before = self._text_output.size()
        if self._page_types[index] == PAGE_TEXT:
            text, failure = self._read_native_page(position, index)
        else:
            text, failure = self._read_scanned_page(position, index)

        if failure is None:
            self._failure_streak.clear()
        else:
            text = self._record_failure(position, index, failure, size_before)
        self._save_page(position, index, text)

    def _read_native_page(self, position: int, index: int) -> tuple[str | None, str | None]:
        self._notify(events.DIRECT, position + 1, len(self._included))
        if not self._settings.wants_text:
            return None, None
        try:
            if self._native_doc is None:
                self._native_doc = open_pdf(self._pdf_path)      # opened once, on first use
            return extract_text_direct(self._pdf_path, index, doc=self._native_doc), None
        except Exception as exc:
            return None, f"its text could not be extracted ({short_reason(exc)})"

    def _read_scanned_page(self, position: int, index: int) -> tuple[str | None, str | None]:
        total = len(self._included)
        self._notify(events.OCR, position + 1, total)

        def on_message(message: str) -> None:
            self._notify(events.KEY, message, position + 1, total)

        outcome = self._page_ocr.run(
            index, self._image_paths.get(index), self._render_failures.get(index), on_message,
        )
        result = outcome.result
        if result is None:
            return None, outcome.failure
        if result.confidence is not None:
            self._ocr_confidences.append(result.confidence)
        if self._settings.wants_searchable_pdf and result.pdf_bytes:
            fragment_path = page_fragment_path(self._paths.images_dir, index)
            write_bytes_atomically(fragment_path, result.pdf_bytes)
        return result.text, None

    def _record_failure(self, position: int, index: int, failure: str, size_before: int | None) -> str:
        """Notes an unreadable page and returns the placeholder text for it."""
        self._failure_streak.append((position, size_before))
        if len(self._failure_streak) >= MAX_CONSECUTIVE_PAGE_FAILURES:
            self._abort_after_failure_streak(index, failure)
        self._failed_pages[index + 1] = failure
        self._notify(events.PAGE_FAILED, index + 1, failure, len(self._failed_pages))
        return page_failure_text(index + 1, failure)

    def _abort_after_failure_streak(self, index: int, failure: str) -> None:
        """Takes the failed run back out — the text written for it, and its place
        in the progress record — so that Resume, after the cause is fixed,
        retries these pages. Then stops the job."""
        first_position, first_size = self._failure_streak[0]
        for earlier_position, _size in self._failure_streak[:-1]:
            self._failed_pages.pop(self._included[earlier_position] + 1, None)
        if first_size is not None:
            self._text_output.truncate_to(first_size)
            self._data["txt_size"] = first_size
        self._data["completed_pages"] = first_position
        self._data["failed_pages"] = self._failed_pages_for_saving()
        self._progress.save()

        first_page, last_page = self._included[first_position] + 1, index + 1
        raise RuntimeError(
            f"{len(self._failure_streak)} pages in a row could not be read (pages {first_page}\u2013{last_page}). "
            f"Last error: {failure}\n\n"
            "That usually points to a problem with the setup — the OCR language, "
            "Tesseract or available memory — rather than with the pages themselves."
        )

    def _failed_pages_for_saving(self) -> dict[str, str]:
        return {str(page): reason for page, reason in self._failed_pages.items()}

    def _save_page(self, position: int, index: int, text: str | None) -> None:
        if self._settings.wants_text:
            self._data["txt_size"] = self._text_output.write_page(
                index + 1, text, self._settings.page_numbers,
            )
        self._data["completed_pages"] = position + 1
        self._data["ocr_confidences"] = self._ocr_confidences
        self._data["failed_pages"] = self._failed_pages_for_saving()
        self._progress.save()

    # ── Finalize ──────────────────────────────────────────────────────

    def _finalize(self) -> None:
        if self._settings.wants_searchable_pdf:
            self._notify(events.STAGE, "Assembling searchable PDF…")
            assemble_pdf(
                self._pdf_path, self._paths, self._page_types, self._included,
                failed_indices={page - 1 for page in self._failed_pages},
            )
        self._data["status"] = STATUS_COMPLETED
        self._progress.save()
        remove_work_dir(self._paths.images_dir)
        self._progress.delete()

    def _build_result(self) -> BookResult:
        settings = self._settings
        confidences = self._ocr_confidences
        return BookResult(
            txt_path=self._paths.txt_path if settings.wants_text else None,
            pdf_path=self._paths.pdf_path if settings.wants_searchable_pdf else None,
            total_pages=len(self._included),
            ocr_pages=len(self._scanned_indices()),
            avg_confidence=sum(confidences) / len(confidences) if confidences else None,
            low_text_pages=int(self._data.get("low_text_pages", 0)) if settings.image_mode == IMAGE_MODE_OFF else 0,
            failed_pages=dict(sorted(self._failed_pages.items())),
        )


def run_book_extraction(
    request: BookRequest,
    progress_cb,
    cancel_event: threading.Event,
    resume: bool = False,
) -> BookResult:
    """
    Runs the hybrid pipeline for *request*.

    :param progress_cb:  progress_cb(kind, *args) — see core/book/events.py.
    :param cancel_event: when set, the run stops with CancelledError, leaving
                         a progress record that a later resume continues from.
    :param resume:       continue the saved job for this PDF if there is one
                         (it then keeps the settings it started with).
    """
    return BookExtraction(request, progress_cb, cancel_event, resume).run()
