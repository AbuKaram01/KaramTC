# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The "extraction complete" page of the PDF tab.

Shows what was produced, which pages need attention, and buttons to open the results.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from core.book import BookResult
from ui.widgets import centered_row, pill_button

# Longer lists of failed page numbers are truncated, so that the summary stays readable.
_MAX_FAILED_PAGES_SHOWN = 12


def _failed_pages_line(result: BookResult) -> str:
    """Return the warning about unreadable pages and where they are marked in each output."""
    numbers = sorted(result.failed_pages)
    shown = ", ".join(str(number) for number in numbers[:_MAX_FAILED_PAGES_SHOWN])
    if len(numbers) > _MAX_FAILED_PAGES_SHOWN:
        shown += f" \u2026 and {len(numbers) - _MAX_FAILED_PAGES_SHOWN} more"
    where = []
    if result.txt_path:
        where.append("marked \u201c[\u26a0 Page N could not be read\u2026]\u201d in the text file")
    if result.pdf_path:
        where.append("kept as the original page, without searchable text, in the PDF")
    return (
        f"\u26a0 {len(numbers)} page(s) could not be read and were skipped: {shown}\n"
        f"They are {' and '.join(where)}. You can extract just those pages again "
        "from \u201cPages to extract\u201d."
    )


def describe_result(result: BookResult) -> str:
    """Return the summary text shown on the completion page."""
    lines = [f"Extracted {result.total_pages} pages"]
    if result.ocr_pages:
        confidence = (
            f" (avg. OCR confidence {result.avg_confidence:.0f}%)" if result.avg_confidence is not None else ""
        )
        lines.append(f"{result.ocr_pages} of them via OCR{confidence}")
    if result.low_text_pages:
        lines.append(
            f"\u26a0 {result.low_text_pages} page(s) had little or no native text and were not "
            "OCR\u2019d (Force image mode is Off) \u2014 they may be empty or incomplete"
        )
    if result.failed_pages:
        lines.append(_failed_pages_line(result))
    saved = [path for path in (result.txt_path, result.pdf_path) if path]
    lines.append("Saved to:\n" + "\n".join(saved))
    return "\n".join(lines) + "\n\nTemporary image files were automatically removed."


class DonePage:
    """The completion page; put `widget` into the tab.

    Adw.StatusPage is a final type and cannot be subclassed, hence composition.

    Args:
        on_new_book: Called when the user presses "New book".
        on_error: Called with a message when a result file or folder cannot be opened.
    """

    def __init__(self, on_new_book, on_error):
        self.widget = Adw.StatusPage()
        self.widget.set_icon_name("object-select-symbolic")
        self.widget.set_title("Extraction complete ✓")
        self._on_error = on_error
        self._txt_path: str | None = None
        self._pdf_path: str | None = None
        self._folder: str | None = None

        # Distinct icons and visible labels: the text file, the PDF and the folder are three different targets
        # and must be distinguishable at a glance.
        self._open_text_button = pill_button(
            "Open text file", "text-x-generic-symbolic", lambda *_: self._open(self._txt_path), suggested=True,
        )
        self._open_pdf_button = pill_button(
            "Open PDF", "x-office-document-symbolic", lambda *_: self._open(self._pdf_path),
        )
        open_folder_button = pill_button(
            "Open folder", "folder-open-symbolic", lambda *_: self._open(self._folder),
            tooltip="Show the output folder in the file manager",
        )
        new_book_button = pill_button("New book", "list-add-symbolic", on_new_book, tooltip="Choose another PDF")
        self.widget.set_child(centered_row(
            self._open_text_button, self._open_pdf_button, open_folder_button, new_book_button,
        ))

    def show_result(self, result: BookResult, output_dir: str) -> None:
        """Display a finished extraction; buttons for outputs that were not produced are hidden."""
        self._txt_path = result.txt_path
        self._pdf_path = result.pdf_path
        self._folder = output_dir
        self._open_text_button.set_visible(bool(result.txt_path))
        self._open_pdf_button.set_visible(bool(result.pdf_path))
        self._open_text_button.set_tooltip_text(result.txt_path or None)
        self._open_pdf_button.set_tooltip_text(result.pdf_path or None)
        self.widget.set_description(describe_result(result))

    def set_visible(self, visible: bool) -> None:
        """Show or hide the page."""
        self.widget.set_visible(visible)

    def forget_result(self) -> None:
        """Drop the remembered output paths, so that a stale result cannot be opened."""
        self._txt_path = self._pdf_path = self._folder = None

    def _open(self, path: str | None) -> None:
        """Open a file or folder with the default application; failures are reported through `on_error`."""
        if not path:
            return
        try:
            Gtk.show_uri(self.widget.get_root(), Gio.File.new_for_path(path).get_uri(), 0)
        except Exception:
            self._on_error("Could not open path")
