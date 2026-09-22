# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/pdf_tab/page.py — The PDF tab: choose a book, extract it, resume it.

Handles UI only; all extraction logic lives in core/book.
"""
from __future__ import annotations

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

import settings as app_settings
from config import PDF_SUPPORTED_EXT
from core.book import BookRequest, CancelledError, find_saved_job, pdf_page_count, run_book_extraction
from ui import dialogs, file_dialogs, saved_settings
from ui.language_selector import LanguageSelector
from ui.ocr_settings import present_ocr_settings
from ui.page_selection import PageSelectionDialog
from ui.pdf_tab import job_setup
from ui.pdf_tab.done_view import DonePage
from ui.pdf_tab.options import BookOptions
from ui.pdf_tab.progress_view import ProgressCard
from ui.pdf_tab.source_rows import SourceRows
from ui.widgets import (
    add_file_drop_target, centered_row, pill_button, scrolled_clamp, set_button_text, status_page,
)

_MODE_SELECT, _MODE_PROGRESS, _MODE_DONE = "select", "progress", "done"
_START_LABEL = "Start extraction"
_RESTART_LABEL = "Start over"


class PdfTab(Adw.Bin):
    """Embeddable PDF-extraction tab (no page-navigation chrome of its own —
    it lives inside the main window's tab switcher)."""

    def __init__(self, on_settings_changed=None, on_running_changed=None):
        """
        :param on_settings_changed: called when OCR Settings changes in a way
            that could affect which languages are available, so the parent
            window can refresh the other tab too. Without it, only this tab
            is refreshed.
        :param on_running_changed: called whenever an extraction starts or
            ends, so the parent window can lock OCR Settings while one runs.
        """
        super().__init__()
        self._on_settings_changed = on_settings_changed
        self._on_running_changed = on_running_changed

        self._pdf_path: str | None = None
        self._output_dir: str | None = None
        self._page_count: int | None = None
        self._excluded_pages: set[int] = set()
        self._resume_data: dict | None = None       # progress of an interrupted job for this PDF
        self._cancel_event = threading.Event()
        self._is_running = False

        self._build_layout()
        self._set_mode(_MODE_SELECT)

    # ── Public interface (used by the main window) ────────────────────

    def is_running(self) -> bool:
        """True while an extraction is in progress — checked before quitting
        so the user isn't caught by a silent, unwarned exit."""
        return self._is_running

    def set_settings_enabled(self, enabled: bool) -> None:
        self._language.set_settings_enabled(enabled)

    def refresh_languages(self) -> None:
        """Called after OCR Settings changes the source or downloads/deletes a language."""
        self._language.refresh()

    # ── Layout ────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self._toast_overlay = Adw.ToastOverlay()
        self.set_child(self._toast_overlay)
        scroll, clamp = scrolled_clamp(maximum_size=620, tightening_threshold=480)
        self._toast_overlay.set_child(scroll)

        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._outer.set_margin_top(6)
        clamp.set_child(self._outer)
        add_file_drop_target(self, self._on_drop)

        self._build_empty_state()
        self._build_file_group()
        self._build_start_controls()
        self._progress_card = ProgressCard(on_stop=self._on_stop)
        self._outer.append(self._progress_card)
        self._done_page = DonePage(on_new_book=self._on_new_book, on_error=self._toast)
        self._outer.append(self._done_page.widget)

    def _build_empty_state(self) -> None:
        self._intro_page = status_page(
            "x-office-document-symbolic", "Choose a PDF file",
            "Drag a PDF here or press the button below\n"
            "Native text pages are extracted directly — "
            "scanned pages are converted to images and OCR\u2019d\n"
            "Set \u201cForce image mode\u201d to On to OCR every page regardless",
        )
        self._outer.append(self._intro_page)
        self._choose_box = centered_row(
            pill_button("Open PDF…", "document-open-symbolic", self._on_choose_pdf, suggested=True)
        )
        self._outer.append(self._choose_box)

    def _build_file_group(self) -> None:
        self._file_group = Adw.PreferencesGroup()
        self._outer.append(self._file_group)

        self._source = SourceRows(
            on_change_pdf=self._on_choose_pdf, on_change_output=self._on_choose_output,
            on_reset_output=self._on_reset_output, on_choose_pages=self._on_choose_pages,
        )
        self._source.set_reset_visible(bool(app_settings.get(saved_settings.PDF_OUTPUT_DIR, "")))
        self._source.add_to(self._file_group)

        self._language = LanguageSelector(
            "OCR language", self._on_open_ocr_settings,
            subtitle="Applied to scanned pages only — text pages are extracted directly",
        )
        self._file_group.add(self._language.row)

        self._options = BookOptions(on_image_mode_changed=self._show_image_mode_effect)
        self._options.add_to(self._file_group)
        # Rows are added in this order: ..., language, format, numbers, contrast, image mode.

    def _build_start_controls(self) -> None:
        self._resume_banner = Adw.Banner(button_label="Resume")
        self._resume_banner.connect("button-clicked", lambda *_: self._on_start(resume=True))
        self._outer.append(self._resume_banner)

        self._start_button = pill_button(
            _START_LABEL, "media-playback-start-symbolic", self._on_start_clicked, suggested=True,
        )
        self._start_button.set_halign(Gtk.Align.CENTER)
        self._outer.append(self._start_button)

    def _show_image_mode_effect(self, choice) -> None:
        self._language.set_subtitle(choice.language_subtitle)

    def _set_mode(self, mode: str) -> None:
        has_pdf = bool(self._pdf_path)
        selecting = mode == _MODE_SELECT
        show_empty = selecting and not has_pdf
        self._intro_page.set_visible(show_empty)
        self._choose_box.set_visible(show_empty)
        self._file_group.set_visible(selecting and has_pdf)
        self._resume_banner.set_revealed(selecting and self._resume_data is not None)
        self._start_button.set_visible(selecting and has_pdf)
        self._progress_card.set_visible(mode == _MODE_PROGRESS)
        self._done_page.set_visible(mode == _MODE_DONE)

    def _set_running(self, running: bool) -> None:
        self._is_running = running
        if self._on_running_changed:
            self._on_running_changed()

    def _toast(self, message: str) -> None:
        dialogs.show_toast(self._toast_overlay, message)

    # ── OCR Settings ──────────────────────────────────────────────────

    def _on_open_ocr_settings(self, *_) -> None:
        present_ocr_settings(
            self.get_root(), on_changed=self._on_settings_changed or self.refresh_languages,
        )

    # ── Choosing the PDF ──────────────────────────────────────────────

    def _on_drop(self, _target, value, _x, _y) -> bool:
        if self._is_running:
            self._toast("An extraction is already running \u2014 stop it first")
            return False
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path and os.path.splitext(path)[1].lower() in PDF_SUPPORTED_EXT:
                self._set_pdf(path)
                return True
        self._toast("Unsupported file — please use a PDF")
        return False

    def _on_choose_pdf(self, *_) -> None:
        pdf_filter = file_dialogs.make_filter(
            "PDF files", mime_types=["application/pdf"], patterns=["*.pdf"], suffixes=PDF_SUPPORTED_EXT,
        )
        file_dialogs.open_file(
            self.get_root(), "Open PDF file", [pdf_filter], self._set_pdf,
            # e.g. a network location opened through the file portal that has no local path
            on_not_local=lambda: self._toast("Please choose a PDF stored on this computer"),
        )

    def _set_pdf(self, path: str) -> None:
        self._pdf_path = path
        self._output_dir = self._remembered_output_dir() or os.path.dirname(os.path.abspath(path)) or None
        # Keep the reset button in step with the stored setting, including when the
        # remembered folder is currently unusable (the user may want to clear it).
        self._source.set_reset_visible(bool(app_settings.get(saved_settings.PDF_OUTPUT_DIR, "")))
        self._done_page.forget_result()
        self._excluded_pages = set()

        self._source.show_pdf_name(os.path.basename(path))
        try:
            self._page_count = pdf_page_count(path)
        except Exception as exc:
            # Encrypted, damaged, empty, or not really a PDF: say so and stay on
            # the "choose a PDF" page rather than offering a Start button that
            # can only fail the same way.
            self._toast(str(exc) or "This file could not be opened as a PDF")
            self._reset()
            return
        self._source.show_pdf_details(self._describe_pdf(path))
        self._source.show_pages(self._page_count, 0)
        self._source.set_output_folder(self._output_dir or "—")
        self._check_resume(search_pdf_folder=True)
        self._set_mode(_MODE_SELECT)

    def _describe_pdf(self, path: str) -> str:
        details = f"{self._page_count} pages"
        try:
            size_mb = os.path.getsize(path) / (1024 * 1024)
        except OSError:
            return details
        return f"{size_mb:.1f} MB  \u2022  {details}"

    def _on_new_book(self, *_) -> None:
        """'New book' goes straight to the file chooser — resetting to the
        empty page first and making the user click "Open PDF…" again is an
        extra step nobody wants after finishing a book."""
        self._reset()
        self._on_choose_pdf()

    def _reset(self) -> None:
        self._pdf_path = self._output_dir = self._page_count = None
        self._resume_data = None
        self._done_page.forget_result()
        self._excluded_pages = set()
        self._source.clear()
        self._source.show_pages(None, 0)
        self._resume_banner.set_revealed(False)
        self._set_mode(_MODE_SELECT)

    # ── Output folder ─────────────────────────────────────────────────

    def _on_choose_output(self, *_) -> None:
        initial = self._output_dir if self._output_dir and os.path.isdir(self._output_dir) else None
        file_dialogs.choose_folder(self.get_root(), "Choose output folder", initial, self._on_output_chosen)

    def _on_output_chosen(self, folder: str) -> None:
        self._output_dir = folder
        self._source.set_output_folder(folder)
        # Remembered for every book from now on, until the user picks another
        # folder or presses the reset button.
        app_settings.set(saved_settings.PDF_OUTPUT_DIR, folder)
        self._source.set_reset_visible(True)
        self._check_resume()
        self._set_mode(_MODE_SELECT)

    def _remembered_output_dir(self) -> str | None:
        """The folder the user last chose, if it is still usable. A folder that
        has since been deleted or unmounted (USB drive, network share…) falls
        back to saving next to the PDF — with a heads-up — instead of failing
        at the end of a long extraction."""
        saved = app_settings.get(saved_settings.PDF_OUTPUT_DIR, "")
        if not saved:
            return None
        if os.path.isdir(saved) and os.access(saved, os.W_OK | os.X_OK):
            return saved
        self._toast("The remembered output folder isn\u2019t available \u2014 saving next to the PDF instead")
        return None

    def _on_reset_output(self, *_) -> None:
        app_settings.remove(saved_settings.PDF_OUTPUT_DIR)
        self._source.set_reset_visible(False)
        if self._pdf_path:
            self._output_dir = os.path.dirname(os.path.abspath(self._pdf_path)) or None
            self._source.set_output_folder(self._output_dir or "\u2014")
            self._check_resume()
            self._set_mode(_MODE_SELECT)
        self._toast("Saving next to each PDF again")

    # ── Pages to extract ──────────────────────────────────────────────

    def _on_choose_pages(self, *_) -> None:
        if not self._pdf_path or not self._page_count:
            return
        PageSelectionDialog(
            self._pdf_path, self._page_count, self._excluded_pages, on_done=self._on_pages_chosen,
        ).present(self.get_root())

    def _on_pages_chosen(self, excluded_pages: set[int]) -> None:
        self._excluded_pages = excluded_pages
        self._source.show_pages(self._page_count, len(self._excluded_pages))

    # ── Resume ────────────────────────────────────────────────────────

    def _check_resume(self, search_pdf_folder: bool = False) -> None:
        """
        Offers to resume an interrupted job for the current PDF.

        *search_pdf_folder* is for when a book has just been opened: a job
        interrupted before an output folder was being remembered (or while a
        different one was) lives next to the PDF, so look there too and switch
        to that folder, rather than silently starting a second job. It is not
        used after the user picks a folder by hand — that choice stands.
        """
        self._resume_data = None
        if not self._pdf_path:
            return
        job = find_saved_job(self._pdf_path, self._output_dir, also_search_pdf_folder=search_pdf_folder)
        if job is not None and job.output_dir != self._output_dir:
            self._output_dir = job.output_dir
            self._source.set_output_folder(job.output_dir)
        # A saved job exists for this path — but if the file itself has since
        # been replaced with different content (same name, new PDF), resuming
        # would silently mix pages from two different documents. Discard the
        # stale progress instead of offering to resume it.
        if job is not None and job.progress.pdf_was_replaced(self._pdf_path):
            job.progress.delete()
            job = None

        if job is None:
            set_button_text(self._start_button, _START_LABEL)
            self._options.load_remembered()
            return
        self._offer_resume(job.progress.data)

    def _offer_resume(self, data: dict) -> None:
        self._resume_data = data
        self._restore_options_from_job(data)
        total = data.get("total_pages") or self._page_count or 0
        done = data.get("completed_pages", 0)
        self._resume_banner.set_title(
            f"Interrupted at page {done} of {total} \u2014 Resume uses the "
            "original settings; use \u201cStart over\u201d to change them"
            if total else
            "Interrupted before analysis completed \u2014 you can resume"
        )
        set_button_text(self._start_button, _RESTART_LABEL)

    def _restore_options_from_job(self, data: dict) -> None:
        self._options.load_from_job(data)
        saved_lang = data.get("lang")
        if saved_lang:
            self._language.select_code(saved_lang)
        saved_excluded = data.get("excluded_pages")
        if saved_excluded is not None:
            self._excluded_pages = set(saved_excluded)
            self._source.show_pages(self._page_count, len(self._excluded_pages))

    # ── Starting an extraction ────────────────────────────────────────

    def _on_start_clicked(self, *_) -> None:
        if self._resume_data is not None:
            dialogs.confirm(
                self.get_root(), "Start over?",
                "Saved progress will be deleted and extraction restarts from page 1.",
                accept_id="restart", accept_label=_RESTART_LABEL, on_accept=lambda: self._on_start(resume=False),
            )
            return
        # A brand-new run overwrites its output files. If some already exist —
        # a previous extraction of this book, or an unrelated file that just
        # shares the name — never replace them without asking.
        existing = job_setup.existing_outputs(self._pdf_path, self._output_dir, self._options.output_format)
        if existing:
            self._confirm_replace(existing)
            return
        self._on_start(resume=False)

    def _confirm_replace(self, existing: list[str]) -> None:
        names = "\n".join(f"\u2022 {name}" for name in existing)
        dialogs.confirm(
            self.get_root(),
            "Replace existing file?" if len(existing) == 1 else "Replace existing files?",
            f"This folder already contains:\n{names}\n\n"
            "Starting will replace it. To keep it, cancel and choose another output folder, "
            "or move or rename the file first.",
            accept_id="replace", accept_label="Replace", on_accept=lambda: self._on_start(resume=False),
        )

    def _on_start(self, resume: bool) -> None:
        if not self._pdf_path:
            return
        problem = job_setup.problem_blocking_start(
            self._options.image_mode, self._language.has_languages, self._page_count, len(self._excluded_pages),
        )
        if problem:
            self._toast(problem)
            return
        output_dir = self._output_dir or os.path.dirname(os.path.abspath(self._pdf_path))
        if not job_setup.output_folder_is_usable(output_dir):
            self._toast(f"Can\u2019t save to \u201c{output_dir}\u201d \u2014 choose another output folder")
            return

        request = job_setup.build_request(
            self._pdf_path, output_dir, self._language.selected_code(), self._options, self._excluded_pages,
        )
        app_settings.set(saved_settings.LAST_OCR_LANG, request.settings.lang)
        self._cancel_event = threading.Event()
        self._set_running(True)
        self._progress_card.start(os.path.basename(self._pdf_path))
        self._set_mode(_MODE_PROGRESS)
        threading.Thread(
            target=self._worker, args=(request, resume, self._cancel_event), daemon=True,
        ).start()

    def _worker(self, request: BookRequest, resume: bool, cancel_event: threading.Event) -> None:
        try:
            result = run_book_extraction(request, self._progress_cb, cancel_event, resume=resume)
            GLib.idle_add(self._on_book_done, result, request.paths.output_dir)
        except CancelledError:
            GLib.idle_add(self._on_book_cancelled)
        except Exception as exc:
            GLib.idle_add(self._on_book_error, str(exc))

    def _on_stop(self, *_) -> None:
        self._cancel_event.set()
        self._progress_card.show_stopping()

    # ── Progress and completion (called on the main thread) ───────────

    def _progress_cb(self, kind: str, *args) -> None:
        GLib.idle_add(self._on_progress_event, kind, *args)

    def _on_progress_event(self, kind: str, *args) -> bool:
        self._progress_card.update(kind, *args)
        return GLib.SOURCE_REMOVE

    def _on_book_done(self, result, output_dir: str) -> bool:
        self._set_running(False)
        self._resume_data = None
        self._done_page.show_result(result, output_dir)
        self._set_mode(_MODE_DONE)
        self._toast("Book extracted successfully ✓")
        return GLib.SOURCE_REMOVE

    def _on_book_cancelled(self) -> bool:
        self._set_running(False)
        self._check_resume()
        self._set_mode(_MODE_SELECT)
        self._toast("Stopped — progress saved, you can resume at any time")
        return GLib.SOURCE_REMOVE

    def _on_book_error(self, message: str) -> bool:
        self._set_running(False)
        self._check_resume()
        self._set_mode(_MODE_SELECT)
        # Only promise a Resume if there really is a saved job: failures before
        # the first page (unreadable PDF, no usable text, folder not writable…)
        # leave nothing to resume.
        suffix = "\n\nProgress was saved — press Resume to try again." if self._resume_data is not None else ""
        dialogs.show_message_dialog(self.get_root(), "Extraction error", f"{message}{suffix}")
        return GLib.SOURCE_REMOVE
