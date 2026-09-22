# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/progress_frame.py — The card shown while a long job runs: title, bar, detail line, Stop.

Each tab subclasses it to turn its own progress events into these four widgets.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ui.widgets import dim_label, labeled_button

_STOPPING_MESSAGE = "Stopping and saving progress…"


class ProgressFrame(Gtk.Frame):
    def __init__(self, on_stop):
        super().__init__()
        self.add_css_class("card")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for setter in (content.set_margin_top, content.set_margin_bottom,
                       content.set_margin_start, content.set_margin_end):
            setter(16)
        self.set_child(content)

        self._title = Gtk.Label(label="Preparing…")
        self._title.add_css_class("title-4")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_wrap(True)
        content.append(self._title)

        self._bar = Gtk.ProgressBar()
        self._bar.set_show_text(True)
        content.append(self._bar)

        self._detail = dim_label(caption=True)
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_wrap(True)
        content.append(self._detail)

        self._stop_button = labeled_button("Stop", "media-playback-stop-symbolic")
        self._stop_button.add_css_class("destructive-action")
        self._stop_button.connect("clicked", on_stop)
        stop_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        stop_row.set_halign(Gtk.Align.END)
        stop_row.append(self._stop_button)
        content.append(stop_row)

    def reset(self, title: str) -> None:
        """Back to the start of a new job."""
        self._stop_button.set_sensitive(True)
        self._title.set_text(title)
        self._bar.set_fraction(0.0)
        self._bar.set_text("")
        self._detail.set_text("")

    def show_stopping(self) -> None:
        self._stop_button.set_sensitive(False)
        self._detail.set_text(_STOPPING_MESSAGE)

    def _set_progress(self, fraction: float, text: str) -> None:
        self._bar.set_fraction(fraction)
        self._bar.set_text(text)
