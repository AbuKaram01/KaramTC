# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/done_view.py — The "transcription complete" page.
"""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from core.media import MediaResult, format_clock, language_name
from ui.widgets import centered_row, pill_button


def describe_result(result: MediaResult) -> str:
    """The summary text shown on the completion page."""
    language = language_name(result.language)
    if result.language_probability is not None:
        language += f" ({result.language_probability * 100:.0f}% sure)"
    lines = [
        f"{format_clock(result.duration)} of audio  •  {result.segment_count} segments  •  {language}",
    ]
    if result.resumed_segments:
        lines.append(f"Continued an earlier run — {result.resumed_segments} segments were kept from it")
    lines.append("Saved to:\n" + result.output_path)
    return "\n".join(lines)


class DonePage:
    """The completion page; put `widget` into the tab. (Adw.StatusPage is a
    final type and cannot be subclassed, hence composition.)"""

    def __init__(self, on_new_file, on_copied, on_error):
        self.widget = Adw.StatusPage()
        self.widget.set_icon_name("object-select-symbolic")
        self.widget.set_title("Transcription complete ✓")
        self._on_copied = on_copied
        self._on_error = on_error
        self._result: MediaResult | None = None

        self.widget.set_child(centered_row(
            pill_button("Open file", "text-x-generic-symbolic", lambda *_: self._open(self._path()), suggested=True),
            pill_button("Open folder", "folder-open-symbolic", lambda *_: self._open(self._folder()),
                        tooltip="Show the output folder in the file manager"),
            pill_button("Copy text", "edit-copy-symbolic", self._copy, tooltip="Copy the transcript to the clipboard"),
            pill_button("New file", "list-add-symbolic", on_new_file, tooltip="Choose another recording"),
        ))

    def show_result(self, result: MediaResult) -> None:
        self._result = result
        self.widget.set_description(describe_result(result))

    def set_visible(self, visible: bool) -> None:
        self.widget.set_visible(visible)

    def _path(self) -> str | None:
        return self._result.output_path if self._result else None

    def _folder(self) -> str | None:
        return os.path.dirname(self._result.output_path) if self._result else None

    def _copy(self, *_) -> None:
        if self._result:
            self.widget.get_clipboard().set(self._result.text)
            self._on_copied()

    def _open(self, path: str | None) -> None:
        if not path:
            return
        try:
            Gtk.show_uri(self.widget.get_root(), Gio.File.new_for_path(path).get_uri(), 0)
        except Exception:
            self._on_error("Could not open path")
