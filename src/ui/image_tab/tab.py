# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/image_tab/tab.py — The Image tab: one picture in, its text out.
"""
from __future__ import annotations

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

import settings as app_settings
from config import PDF_SUPPORTED_EXT, PROVIDER_TESSERACT, SUPPORTED_EXT, SUPPORTED_MIME
from providers.registry import run_ocr
from ui import dialogs, file_dialogs, saved_settings
from ui.image_tab.form import ImageForm
from ui.image_tab.preview import build_preview_texture
from ui.image_tab.result_view import ImageResultView

_FORM, _RESULT = "form", "result"
_BUSY_MESSAGE = "An extraction is already running \u2014 wait for it to finish"
_NOT_LOCAL_MESSAGE = "Only local files are supported"


class ImageTab(Gtk.Stack):
    def __init__(self, on_open_settings, on_busy_changed, show_toast):
        """
        :param on_open_settings: called when the OCR Settings gear is pressed.
        :param on_busy_changed:  called whenever an extraction starts or ends,
                                 so the window can lock OCR Settings meanwhile.
        :param show_toast:       shows a short message (the window owns the overlay).
        """
        super().__init__()
        self._on_busy_changed = on_busy_changed
        self._show_toast = show_toast
        self._image_path: str | None = None
        self._searchable_pdf: bytes | None = None
        self._extracting = False

        self._form = ImageForm(
            on_choose_image=self._on_choose_image, on_extract=self._on_extract,
            on_open_settings=on_open_settings, on_drop=self._on_drop,
        )
        self._result = ImageResultView(
            on_new_image=self._on_new_image, on_copy=self._on_copy,
            on_save_text=self._on_save_text, on_save_pdf=self._on_save_pdf,
        )
        self.add_named(self._form.widget, _FORM)
        self.add_named(self._result, _RESULT)
        self._update_extract_button()

    # ── Public interface (used by the main window) ────────────────────

    def is_busy(self) -> bool:
        return self._extracting

    def set_settings_enabled(self, enabled: bool) -> None:
        self._form.language.set_settings_enabled(enabled)

    def refresh_languages(self) -> None:
        self._form.language.refresh()
        self._update_extract_button()

    # ── Choosing an image ─────────────────────────────────────────────

    def _on_drop(self, _target, value, _x, _y) -> bool:
        if self._extracting:
            self._show_toast(_BUSY_MESSAGE)
            return False
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path and os.path.splitext(path)[1].lower() in SUPPORTED_EXT:
                self._set_image(path)
                return True
        self._show_toast("Unsupported file \u2014 use JPEG, PNG, or WebP")
        return False

    def _on_choose_image(self, *_) -> None:
        if self._extracting:
            self._show_toast(_BUSY_MESSAGE)
            return
        image_filter = file_dialogs.make_filter(
            "Images (JPEG, PNG, WebP)", mime_types=SUPPORTED_MIME, suffixes=SUPPORTED_EXT,
        )
        all_filter = file_dialogs.make_filter("All files", patterns=["*"])
        file_dialogs.open_file(
            self.get_root(), "Open image", [image_filter, all_filter], self._set_image,
            on_not_local=lambda: self._show_toast(_NOT_LOCAL_MESSAGE),
        )

    def _on_new_image(self, *_) -> None:
        """Same flow as the PDF tab's 'New book': straight to the chooser."""
        self._reset()
        self._on_choose_image()

    def _reset(self) -> None:
        self._image_path = None
        self._searchable_pdf = None
        self._form.clear()
        self.set_visible_child_name(_FORM)

    def _set_image(self, path: str) -> None:
        self._image_path = path
        self._searchable_pdf = None
        try:
            preview = build_preview_texture(path)
        except Exception:
            preview = None
        self._form.show_image(os.path.basename(path), self._size_text(path), preview)
        self._update_extract_button()
        # Make sure we're looking at the form, not a stale result from before
        self.set_visible_child_name(_FORM)

    @staticmethod
    def _size_text(path: str) -> str:
        try:
            return f"{os.path.getsize(path) // 1024} KB"
        except OSError:
            # The file could have vanished (unplugged drive, network hiccup, deleted
            # externally) between being picked and landing here — show no size
            # rather than crashing out of the whole selection flow.
            return ""

    def _update_extract_button(self) -> None:
        self._form.set_extract_enabled(self._form.language.has_languages and bool(self._image_path))

    # ── OCR extraction ────────────────────────────────────────────────

    def _on_extract(self, *_) -> None:
        if not self._image_path or not self._form.language.has_languages or self._extracting:
            return
        self._extracting = True
        self._on_busy_changed()
        self._form.set_extract_enabled(False)
        self._form.show_progress(True)
        lang = self._form.language.selected_code()
        app_settings.set(saved_settings.LAST_OCR_LANG, lang)
        # The image path is passed along (not re-read later): if the user somehow
        # picks a different image before this finishes, the worker must still
        # finish processing the one that was actually selected here.
        threading.Thread(target=self._worker, args=(self._image_path, lang), daemon=True).start()

    def _worker(self, image_path: str, lang: str) -> None:
        try:
            # Always ask for a confidence score and a searchable-PDF sidecar — both
            # come out of the same Tesseract invocation as the plain text, so
            # there's no extra cost for a single image.
            options = saved_settings.build_ocr_options(want_pdf=True, want_confidence=True)
            result = run_ocr(
                image_path, PROVIDER_TESSERACT, lang, progress_cb=self._report_progress, options=options,
            )
            GLib.idle_add(self._on_ocr_done, result, None)
        except Exception as exc:
            GLib.idle_add(self._on_ocr_done, None, str(exc))

    def _report_progress(self, message: str) -> None:
        GLib.idle_add(self._form.set_progress_message, message)

    def _on_ocr_done(self, result, error: str | None) -> bool:
        self._extracting = False
        self._on_busy_changed()
        self._form.show_progress(False)
        self._form.set_extract_enabled(True)

        if error:
            dialogs.show_error_dialog(self.get_root(), error)
        elif not result or not result.text:
            self._show_toast("No text found in the image")
        else:
            self._searchable_pdf = result.pdf_bytes
            self._result.show_result(result.text, bool(result.pdf_bytes), result.confidence)
            self.set_visible_child_name(_RESULT)
        return GLib.SOURCE_REMOVE

    # ── Copy / save ───────────────────────────────────────────────────

    def _suggested_name(self, suffix: str) -> str | None:
        if not self._image_path:
            return None
        return os.path.splitext(os.path.basename(self._image_path))[0] + suffix

    def _on_copy(self, *_) -> None:
        self.get_clipboard().set(self._result.text)
        self._show_toast("Text copied to clipboard")

    def _on_save_text(self, *_) -> None:
        file_dialogs.save_file(
            self.get_root(), "Save text", self._suggested_name(".txt"),
            file_dialogs.make_filter("Text files (*.txt)", mime_types=["text/plain"], suffixes=[".txt"]),
            self._write_text, on_not_local=lambda: self._show_toast(_NOT_LOCAL_MESSAGE),
        )

    def _write_text(self, path: str) -> None:
        self._write_file(path, "w", self._result.text, "File saved successfully \u2713", encoding="utf-8")

    def _on_save_pdf(self, *_) -> None:
        if not self._searchable_pdf:
            return
        file_dialogs.save_file(
            self.get_root(), "Save searchable PDF", self._suggested_name("_searchable.pdf"),
            file_dialogs.make_filter("PDF files (*.pdf)", mime_types=["application/pdf"], suffixes=PDF_SUPPORTED_EXT),
            self._write_pdf, on_not_local=lambda: self._show_toast(_NOT_LOCAL_MESSAGE),
        )

    def _write_pdf(self, path: str) -> None:
        self._write_file(path, "wb", self._searchable_pdf, "Searchable PDF saved \u2713")

    def _write_file(self, path: str, mode: str, content, success_message: str, encoding: str | None = None) -> None:
        try:
            with open(path, mode, encoding=encoding) as output_file:
                output_file.write(content)
        except OSError as exc:
            dialogs.show_error_dialog(self.get_root(), str(exc))
            return
        self._show_toast(success_message)
