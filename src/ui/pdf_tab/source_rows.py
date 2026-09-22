# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/pdf_tab/source_rows.py — The rows describing which PDF, where its output goes, and which pages.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from ui.widgets import flat_icon_button, flat_text_button, make_icon_prefix

NO_FILE_TITLE = "\u2014"
_RESET_OUTPUT_TOOLTIP = "Stop remembering this folder \u2014 save next to each PDF again"


def pages_summary(page_count: int | None, excluded_count: int) -> str:
    if not page_count:
        return ""
    if excluded_count == 0:
        return f"All {page_count} pages"
    included = page_count - excluded_count
    return f"{included} of {page_count} pages \u2014 {excluded_count} excluded"


class SourceRows:
    """The PDF row, the output-folder row and the pages row."""

    def __init__(self, on_change_pdf, on_change_output, on_reset_output, on_choose_pages):
        self._file_row = Adw.ActionRow()
        self._file_row.set_use_markup(False)        # file names may contain & or <
        self._file_row.set_title(NO_FILE_TITLE)
        self._file_row.add_prefix(make_icon_prefix("x-office-document-symbolic"))
        self._file_row.add_suffix(flat_text_button("Change", on_change_pdf))

        self._output_row = Adw.ActionRow(title="Output folder")
        self._output_row.set_use_markup(False)      # folder names may contain & or <
        self._output_row.add_prefix(make_icon_prefix("folder-symbolic"))
        # Only shown while a folder is being remembered: the way back to
        # "save next to each PDF".
        self._reset_button = flat_icon_button("edit-undo-symbolic", _RESET_OUTPUT_TOOLTIP, on_reset_output)
        self._output_row.add_suffix(self._reset_button)
        self._output_row.add_suffix(flat_text_button("Change", on_change_output))

        self._pages_row = Adw.ActionRow(title="Pages to extract")
        self._pages_row.add_prefix(make_icon_prefix("view-grid-symbolic"))
        choose_button = flat_text_button("Choose\u2026", on_choose_pages)
        self._pages_row.add_suffix(choose_button)
        self._pages_row.set_activatable_widget(choose_button)

    def add_to(self, group: Adw.PreferencesGroup) -> None:
        for row in (self._file_row, self._output_row, self._pages_row):
            group.add(row)

    def show_pdf_name(self, name: str) -> None:
        self._file_row.set_title(name)

    def show_pdf_details(self, text: str) -> None:
        self._file_row.set_subtitle(text)

    def set_output_folder(self, text: str) -> None:
        self._output_row.set_subtitle(text)

    def set_reset_visible(self, visible: bool) -> None:
        self._reset_button.set_visible(visible)

    def show_pages(self, page_count: int | None, excluded_count: int) -> None:
        self._pages_row.set_subtitle(pages_summary(page_count, excluded_count))

    def clear(self) -> None:
        self._file_row.set_title(NO_FILE_TITLE)
        self._file_row.set_subtitle("")
        self._output_row.set_subtitle("")
