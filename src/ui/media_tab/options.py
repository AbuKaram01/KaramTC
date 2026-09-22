# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/options.py — The Audio/Video tab's option rows: language, format, timestamps.

Choices are remembered between sessions.
"""
from __future__ import annotations

from typing import NamedTuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

import settings as app_settings
from core.media import OUTPUT_SRT, OUTPUT_TXT, OUTPUT_VTT, languages_by_name
from core.media.constants import TEXT_LAYOUT_CONTINUOUS, TEXT_LAYOUT_LINES
from ui import saved_settings
from ui.widgets import make_icon_prefix, string_list, switch_row

AUTO_DETECT_LABEL = "Auto-detect"


class FormatChoice(NamedTuple):
    id: str
    label: str
    subtitle: str


FORMAT_CHOICES = [
    FormatChoice(OUTPUT_TXT, "Text file", "The words only — one line per spoken segment"),
    FormatChoice(OUTPUT_SRT, "Subtitles (SRT)", "Timed subtitles that most video players load"),
    FormatChoice(OUTPUT_VTT, "Subtitles (WebVTT)", "Timed subtitles for web players"),
]
_FORMAT_IDS = [choice.id for choice in FORMAT_CHOICES]

LAYOUT_CHOICES = [
    FormatChoice(TEXT_LAYOUT_CONTINUOUS, "Continuous text", "Everything as one flowing text, with no line breaks"),
    FormatChoice(TEXT_LAYOUT_LINES, "One line per segment", "A new line for each spoken segment — can start each line with its time"),
]
_LAYOUT_IDS = [choice.id for choice in LAYOUT_CHOICES]
_LANGUAGES = languages_by_name()
_LANGUAGE_CODES: list[str | None] = [None] + [code for code, _name in _LANGUAGES]


class MediaOptions:
    def __init__(self, on_format_changed=None):
        """:param on_format_changed: called with the output format id whenever it changes."""
        self._on_format_changed = on_format_changed
        self._build_language_row()
        self._build_format_row()
        self._build_layout_row()
        self._timestamps_row, self._timestamps_switch = switch_row(
            "Timestamps in the text file",
            bool(app_settings.get(saved_settings.MEDIA_TIMESTAMPS, False)),
            lambda switch, _param: app_settings.set(saved_settings.MEDIA_TIMESTAMPS, switch.get_active()),
            subtitle="Starts each line with the time it was said, like [0:12:40]",
        )
        self._update_dependent_rows()

    def add_to(self, group: Adw.PreferencesGroup) -> None:
        for row in (self._language_row, self._format_row, self._layout_row, self._timestamps_row):
            group.add(row)

    # ── Current values ────────────────────────────────────────────────

    @property
    def language(self) -> str | None:
        """The chosen Whisper language code, or None to detect it."""
        selected = self._language_row.get_selected()
        return _LANGUAGE_CODES[selected] if 0 <= selected < len(_LANGUAGE_CODES) else None

    @property
    def output_format(self) -> str:
        selected = self._format_row.get_selected()
        return FORMAT_CHOICES[selected].id if 0 <= selected < len(FORMAT_CHOICES) else OUTPUT_TXT

    @property
    def text_layout(self) -> str:
        selected = self._layout_row.get_selected()
        return LAYOUT_CHOICES[selected].id if 0 <= selected < len(LAYOUT_CHOICES) else TEXT_LAYOUT_CONTINUOUS

    @property
    def timestamps(self) -> bool:
        return self._timestamps_switch.get_active()

    # ── Construction ──────────────────────────────────────────────────

    def _build_language_row(self) -> None:
        row = Adw.ComboRow()
        row.set_title("Spoken language")
        row.set_subtitle("Auto-detect works for most recordings; choose one if it guesses wrong")
        row.add_prefix(make_icon_prefix("preferences-desktop-locale-symbolic"))
        row.set_model(string_list([AUTO_DETECT_LABEL] + [name for _code, name in _LANGUAGES]))
        # A hundred languages: let the user type to find one.
        row.set_enable_search(True)
        row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        saved = app_settings.get(saved_settings.MEDIA_LANGUAGE, "") or None
        row.set_selected(_LANGUAGE_CODES.index(saved) if saved in _LANGUAGE_CODES else 0)
        row.connect("notify::selected", self._on_language_selected)
        self._language_row = row

    def _build_format_row(self) -> None:
        row = Adw.ComboRow()
        row.set_title("Output format")
        row.add_prefix(make_icon_prefix("document-save-symbolic"))
        row.set_model(string_list(choice.label for choice in FORMAT_CHOICES))
        saved = app_settings.get(saved_settings.MEDIA_OUTPUT_FORMAT, OUTPUT_TXT)
        row.set_selected(_FORMAT_IDS.index(saved) if saved in _FORMAT_IDS else 0)
        row.connect("notify::selected", self._on_format_selected)
        self._format_row = row
        self._update_format_subtitle()

    def _build_layout_row(self) -> None:
        row = Adw.ComboRow()
        row.set_title("Text layout")
        row.add_prefix(make_icon_prefix("format-justify-left-symbolic"))
        row.set_model(string_list(choice.label for choice in LAYOUT_CHOICES))
        saved = app_settings.get(saved_settings.MEDIA_TEXT_LAYOUT, TEXT_LAYOUT_CONTINUOUS)
        row.set_selected(_LAYOUT_IDS.index(saved) if saved in _LAYOUT_IDS else 0)
        row.connect("notify::selected", self._on_layout_selected)
        self._layout_row = row
        self._update_layout_subtitle()

    # ── Change handlers ───────────────────────────────────────────────

    def _on_language_selected(self, _row, _param) -> None:
        app_settings.set(saved_settings.MEDIA_LANGUAGE, self.language or "")

    def _on_format_selected(self, _row, _param) -> None:
        app_settings.set(saved_settings.MEDIA_OUTPUT_FORMAT, self.output_format)
        self._update_format_subtitle()
        self._update_dependent_rows()
        if self._on_format_changed:
            self._on_format_changed(self.output_format)

    def _on_layout_selected(self, _row, _param) -> None:
        app_settings.set(saved_settings.MEDIA_TEXT_LAYOUT, self.text_layout)
        self._update_layout_subtitle()
        self._update_dependent_rows()

    def _update_layout_subtitle(self) -> None:
        self._layout_row.set_subtitle(LAYOUT_CHOICES[_LAYOUT_IDS.index(self.text_layout)].subtitle)

    def _update_format_subtitle(self) -> None:
        self._format_row.set_subtitle(FORMAT_CHOICES[_FORMAT_IDS.index(self.output_format)].subtitle)

    def _update_dependent_rows(self) -> None:
        """Subtitle files always carry times and have no text layout. In a text
        file, start times only fit the one-line-per-segment layout."""
        is_text = self.output_format == OUTPUT_TXT
        self._layout_row.set_sensitive(is_text)
        self._timestamps_row.set_sensitive(is_text and self.text_layout == TEXT_LAYOUT_LINES)
