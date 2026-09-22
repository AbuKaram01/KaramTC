# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/pdf_tab/options.py — The PDF tab's per-book option rows.

Output format, page numbers, contrast enhancement and "Force image mode".
Changes are remembered between sessions, except while an option is being
*loaded* (from the remembered choices or from an interrupted job): that is
state to show, not a new preference to save.
"""
from __future__ import annotations

import contextlib
from typing import NamedTuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

import settings as app_settings
from core.book import (
    IMAGE_MODE_AUTO, IMAGE_MODE_OFF, IMAGE_MODE_ON, IMAGE_MODES,
    OUTPUT_BOTH, OUTPUT_PDF, OUTPUT_TXT, normalize_image_mode,
)
from ui import saved_settings
from ui.widgets import make_icon_prefix, string_list, switch_row


class OutputFormatChoice(NamedTuple):
    id: str
    label: str
    subtitle: str


class ImageModeChoice(NamedTuple):
    id: str
    label: str
    subtitle: str           # shown under the "Force image mode" row
    language_subtitle: str  # shown under the OCR language row


OUTPUT_FORMAT_CHOICES = [
    OutputFormatChoice(OUTPUT_TXT, "Text file", "A plain .txt file, as before"),
    OutputFormatChoice(OUTPUT_PDF, "Searchable PDF", "One PDF you can select and search text in \u2014 no .txt file"),
    OutputFormatChoice(OUTPUT_BOTH, "Text file + Searchable PDF", "Both outputs from the same extraction pass"),
]

IMAGE_MODE_CHOICES = [
    ImageModeChoice(
        IMAGE_MODE_AUTO, "Auto",
        "Uses a page's native text when it looks reliable, and OCR for scanned or garbled pages",
        "Applied to scanned pages only \u2014 text pages are extracted directly",
    ),
    ImageModeChoice(
        IMAGE_MODE_ON, "On",
        "Converts every page to an image before OCR, even pages with native text \u2014 "
        "use this if the extracted text appears garbled or distorted",
        "Applied to all pages \u2014 every page is converted to an image first",
    ),
    ImageModeChoice(
        IMAGE_MODE_OFF, "Off",
        "Never OCR \u2014 uses only the text already inside the PDF (fastest). "
        "Scanned pages will come out empty",
        "Not used \u2014 OCR is off, only the PDF\u2019s native text is extracted",
    ),
]

_OUTPUT_FORMAT_IDS = [choice.id for choice in OUTPUT_FORMAT_CHOICES]


def image_mode_choice(mode: str) -> ImageModeChoice:
    return next(choice for choice in IMAGE_MODE_CHOICES if choice.id == mode)


class BookOptions:
    """
    :param on_image_mode_changed: called with the image-mode choice whenever
        the selection changes or is loaded, so the language row's subtitle
        can follow it.
    """

    def __init__(self, on_image_mode_changed):
        self._on_image_mode_changed = on_image_mode_changed
        self._loading = False

        self._build_format_row()
        self._numbers_row, self._numbers_switch = switch_row(
            "Add page numbers to output",
            bool(app_settings.get(saved_settings.PDF_PAGE_NUMBERS, True)),
            lambda switch, _param: self._remember_toggle(saved_settings.PDF_PAGE_NUMBERS, switch),
            subtitle='Inserts "----- Page N -----" before each page\'s text',
        )
        self._enhance_row, self._enhance_switch = switch_row(
            "Enhance contrast for faded pages",
            bool(app_settings.get(saved_settings.PDF_ENHANCE_CONTRAST, False)),
            lambda switch, _param: self._remember_toggle(saved_settings.PDF_ENHANCE_CONTRAST, switch),
            subtitle="Useful for old scanned books with low contrast",
        )
        self._build_image_mode_row()

    def add_to(self, group: Adw.PreferencesGroup) -> None:
        for row in (self._format_row, self._numbers_row, self._enhance_row, self._mode_row):
            group.add(row)

    # ── Current values ────────────────────────────────────────────────

    @property
    def output_format(self) -> str:
        selected = self._format_row.get_selected()
        if 0 <= selected < len(OUTPUT_FORMAT_CHOICES):
            return OUTPUT_FORMAT_CHOICES[selected].id
        return OUTPUT_TXT

    @property
    def page_numbers(self) -> bool:
        return self._numbers_switch.get_active()

    @property
    def enhance_contrast(self) -> bool:
        return self._enhance_switch.get_active()

    @property
    def image_mode(self) -> str:
        selected = self._mode_row.get_selected()
        return IMAGE_MODE_CHOICES[selected].id if 0 <= selected < len(IMAGE_MODE_CHOICES) else IMAGE_MODE_AUTO

    # ── Loading ───────────────────────────────────────────────────────

    def load_remembered(self) -> None:
        """Puts the options back to the user's remembered choices."""
        with self._loading_guard():
            self._numbers_switch.set_active(bool(app_settings.get(saved_settings.PDF_PAGE_NUMBERS, True)))
            self._enhance_switch.set_active(bool(app_settings.get(saved_settings.PDF_ENHANCE_CONTRAST, False)))
            self.set_image_mode(app_settings.get(saved_settings.PDF_IMAGE_MODE, IMAGE_MODE_AUTO))

    def load_from_job(self, data: dict) -> None:
        """
        Restores every option to exactly what the interrupted job will use on
        resume, so the switches never show something different from what
        pressing "Resume" is about to do.
        """
        with self._loading_guard():
            self.set_image_mode(data.get("image_mode", data.get("force_image_mode")))
            self._enhance_switch.set_active(bool(data.get("enhance_contrast")))
            self._numbers_switch.set_active(bool(data.get("page_numbers", True)))
        saved_format = data.get("output_format")
        if saved_format in _OUTPUT_FORMAT_IDS:
            self._format_row.set_selected(_OUTPUT_FORMAT_IDS.index(saved_format))

    def set_image_mode(self, mode) -> None:
        """Selects *mode* and refreshes the explanatory subtitles."""
        self._mode_row.set_selected(IMAGE_MODES.index(normalize_image_mode(mode)))
        self._refresh_image_mode_subtitles()

    # ── Row construction ──────────────────────────────────────────────

    def _build_format_row(self) -> None:
        row = Adw.ComboRow()
        row.set_title("Output format")
        row.add_prefix(make_icon_prefix("document-save-symbolic"))
        row.set_model(string_list(choice.label for choice in OUTPUT_FORMAT_CHOICES))
        saved_format = app_settings.get(saved_settings.OCR_OUTPUT_FORMAT, OUTPUT_TXT)
        row.set_selected(_OUTPUT_FORMAT_IDS.index(saved_format) if saved_format in _OUTPUT_FORMAT_IDS else 0)
        row.connect("notify::selected", self._on_format_changed)
        self._format_row = row
        self._on_format_changed(row, None)

    def _build_image_mode_row(self) -> None:
        row = Adw.ComboRow()
        row.set_title("Force image mode")
        row.add_prefix(make_icon_prefix("camera-photo-symbolic"))
        row.set_model(string_list(choice.label for choice in IMAGE_MODE_CHOICES))
        self._mode_row = row
        self.set_image_mode(app_settings.get(saved_settings.PDF_IMAGE_MODE, IMAGE_MODE_AUTO))
        row.connect("notify::selected", self._on_image_mode_selected)

    # ── Change handlers ───────────────────────────────────────────────

    def _on_format_changed(self, _row, _param) -> None:
        app_settings.set(saved_settings.OCR_OUTPUT_FORMAT, self.output_format)
        subtitle = next((c.subtitle for c in OUTPUT_FORMAT_CHOICES if c.id == self.output_format), "")
        self._format_row.set_subtitle(subtitle)

    def _on_image_mode_selected(self, _row, _param) -> None:
        self._refresh_image_mode_subtitles()
        if not self._loading:
            app_settings.set(saved_settings.PDF_IMAGE_MODE, self.image_mode)

    def _remember_toggle(self, key: str, switch) -> None:
        if not self._loading:
            app_settings.set(key, switch.get_active())

    def _refresh_image_mode_subtitles(self) -> None:
        choice = image_mode_choice(self.image_mode)
        self._mode_row.set_subtitle(choice.subtitle)
        self._on_image_mode_changed(choice)

    @contextlib.contextmanager
    def _loading_guard(self):
        self._loading = True
        try:
            yield
        finally:
            self._loading = False
