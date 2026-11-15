# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The "OCR language" row with its OCR Settings gear.

There is one instance per tab. Each instance re-reads the available languages for the current language source
on refresh(), so every tab follows changes made in OCR Settings.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

import settings as app_settings
from providers.engine_settings import SYSTEM_LANG_SOURCE
from providers.tesseract import DEFAULT_LANG, available_langs_for_source, build_lang_options
from ui import saved_settings
from ui.widgets import flat_icon_button, make_icon_prefix, string_list

# Tooltips of the OCR Settings gear: normal and while an extraction is running.
_SETTINGS_TOOLTIP = "OCR Settings"
_SETTINGS_LOCKED_TOOLTIP = "OCR Settings \u2014 unavailable while an extraction is running"


class LanguageSelector:
    """An Adw.ComboRow of OCR languages with an OCR Settings button as its suffix.

    *title* and *subtitle* label the row; *on_open_settings* is the click handler of the gear button.

    The selector never disables the combo row itself: the OCR Settings gear lives inside it as a suffix, and GTK
    cascades a row's insensitivity down to its children. Disabling the row would make the gear unclickable too,
    locking the user out of the one place that lets them fix a "no languages" situation (switch the source back,
    or download a language). Use set_settings_enabled() to lock the gear alone.
    """

    def __init__(self, title: str, on_open_settings, subtitle: str | None = None):
        self.row = Adw.ComboRow()
        self.row.set_title(title)
        if subtitle:
            self.row.set_subtitle(subtitle)
        self.row.add_prefix(make_icon_prefix("preferences-desktop-locale-symbolic"))
        self._settings_button = flat_icon_button("emblem-system-symbolic", _SETTINGS_TOOLTIP, on_open_settings)
        self.row.add_suffix(self._settings_button)

        self._codes: list[str] = []
        self.refresh()

    @property
    def has_languages(self) -> bool:
        """Whether at least one language is available for the current source."""
        return bool(self._codes)

    def selected_code(self) -> str | None:
        """Return the selected language code, or None if no language is available.

        When none is available the row shows a placeholder message, not a usable language.
        """
        selected = self.row.get_selected()
        if self._codes and selected < len(self._codes):
            return self._codes[selected]
        return None

    def select_code(self, code: str | None) -> None:
        """Select the language *code*; do nothing if it is not in the list."""
        if code in self._codes:
            self.row.set_selected(self._codes.index(code))

    def set_subtitle(self, text: str) -> None:
        """Set the subtitle of the row."""
        self.row.set_subtitle(text)

    def refresh(self) -> None:
        """Re-read the language source and repopulate the row."""
        available = available_langs_for_source(saved_settings.valid_lang_source())
        options = build_lang_options(available)
        self._codes = [code for code, _name in options]
        if options:
            self.row.set_model(string_list(name for _code, name in options))
            self.row.set_selected(self._initial_index())
        else:
            self.row.set_model(string_list([self._no_languages_message()]))

    def set_settings_enabled(self, enabled: bool) -> None:
        """Enable or disable the OCR Settings gear.

        The gear is locked while any extraction is running, because changing or deleting language data mid-run
        could break that job.
        """
        self._settings_button.set_sensitive(enabled)
        self._settings_button.set_tooltip_text(_SETTINGS_TOOLTIP if enabled else _SETTINGS_LOCKED_TOOLTIP)

    def _initial_index(self) -> int:
        """Return the index of the language used last time, else the default, else the first."""
        saved = app_settings.get(saved_settings.LAST_OCR_LANG, DEFAULT_LANG)
        for wanted in (saved, DEFAULT_LANG):
            if wanted in self._codes:
                return self._codes.index(wanted)
        return 0

    @staticmethod
    def _no_languages_message() -> str:
        if saved_settings.valid_lang_source() == SYSTEM_LANG_SOURCE:
            return "No language packs installed \u2014 open OCR Settings"
        return "No languages downloaded for this quality \u2014 open OCR Settings"
