# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The rows that describe which PDF is processed, where its output goes, and which pages are extracted."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from ui.widgets import flat_icon_button, flat_text_button, make_icon_prefix

# Placeholder title of the PDF row while no file is chosen.
NO_FILE_TITLE = "\u2014"
_RESET_OUTPUT_TOOLTIP = "Stop remembering this folder \u2014 save next to each PDF again"


def pages_summary(page_count: int | None, excluded_count: int) -> str:
    """Return the subtitle of the pages row, or an empty string while the page count is unknown."""
    if not page_count:
        return ""
    if excluded_count == 0:
        return f"All {page_count} pages"
    included = page_count - excluded_count
    return f"{included} of {page_count} pages \u2014 {excluded_count} excluded"


class SourceRows:
    """The PDF row, the output-folder row and the pages row.

    Args:
        on_change_pdf: Called when the user presses "Change" on the PDF row.
        on_change_output: Called when the user presses "Change" on the output-folder row.
        on_reset_output: Called when the user presses the button that forgets the remembered output folder.
        on_choose_pages: Called when the user presses "Choose..." on the pages row.
    """

    def __init__(self, on_change_pdf, on_change_output, on_reset_output, on_choose_pages):
        self._file_row = Adw.ActionRow()
        # Names come from the file system and may contain "&" or "<", which markup would misparse.
        self._file_row.set_use_markup(False)
        self._file_row.set_title(NO_FILE_TITLE)
        self._file_row.add_prefix(make_icon_prefix("x-office-document-symbolic"))
        self._file_row.add_suffix(flat_text_button("Change", on_change_pdf))

        self._output_row = Adw.ActionRow(title="Output folder")
        # Same reason as for the file row: folder names may contain "&" or "<".
        self._output_row.set_use_markup(False)
        self._output_row.add_prefix(make_icon_prefix("folder-symbolic"))
        # Only shown while a folder is being remembered: it is the way back to "save next to each PDF".
        self._reset_button = flat_icon_button("edit-undo-symbolic", _RESET_OUTPUT_TOOLTIP, on_reset_output)
        self._output_row.add_suffix(self._reset_button)
        self._output_row.add_suffix(flat_text_button("Change", on_change_output))

        self._pages_row = Adw.ActionRow(title="Pages to extract")
        self._pages_row.add_prefix(make_icon_prefix("view-grid-symbolic"))
        choose_button = flat_text_button("Choose\u2026", on_choose_pages)
        self._pages_row.add_suffix(choose_button)
        self._pages_row.set_activatable_widget(choose_button)

    def add_to(self, group: Adw.PreferencesGroup) -> None:
        """Add the three rows to *group*, in display order."""
        for row in (self._file_row, self._output_row, self._pages_row):
            group.add(row)

    def show_pdf_name(self, name: str) -> None:
        """Show the file name of the chosen PDF."""
        self._file_row.set_title(name)

    def show_pdf_details(self, text: str) -> None:
        """Show details of the chosen PDF (such as its page count) under its name."""
        self._file_row.set_subtitle(text)

    def set_output_folder(self, text: str) -> None:
        """Show where the output files will be written."""
        self._output_row.set_subtitle(text)

    def set_reset_visible(self, visible: bool) -> None:
        """Show or hide the button that forgets the remembered output folder."""
        self._reset_button.set_visible(visible)

    def show_pages(self, page_count: int | None, excluded_count: int) -> None:
        """Summarise which pages will be extracted."""
        self._pages_row.set_subtitle(pages_summary(page_count, excluded_count))

    def clear(self) -> None:
        """Return the PDF and output-folder rows to their empty state."""
        self._file_row.set_title(NO_FILE_TITLE)
        self._file_row.set_subtitle("")
        self._output_row.set_subtitle("")
