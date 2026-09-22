# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/page_selection/zoom_bar.py — Zoom control for the full-size page preview.

Like a phone's volume control: a button on either side of a slider, rather
than a bare slider alone.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ui.widgets import dim_label, flat_icon_button, handler_blocked

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 50, 200, 25     # percent
ZOOM_DEFAULT = 100


class ZoomBar(Gtk.Box):
    def __init__(self, on_zoom_changed):
        """:param on_zoom_changed: called with the zoom as a factor (1.0 = 100 %)."""
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._on_zoom_changed = on_zoom_changed
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(6)
        self.set_margin_bottom(2)

        self.append(flat_icon_button("zoom-out-symbolic", "Zoom out", lambda *_: self._step(-ZOOM_STEP), centered=False))
        self._scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, ZOOM_MIN, ZOOM_MAX, 1)
        self._scale.set_value(ZOOM_DEFAULT)
        self._scale.set_draw_value(False)
        self._scale.set_hexpand(True)
        self._scale.connect("value-changed", self._on_scale_changed)
        self.append(self._scale)
        self.append(flat_icon_button("zoom-in-symbolic", "Zoom in", lambda *_: self._step(ZOOM_STEP), centered=False))

        self._label = dim_label(f"{ZOOM_DEFAULT}%")
        self._label.set_width_chars(5)
        self.append(self._label)

    @property
    def factor(self) -> float:
        return self._scale.get_value() / 100.0

    def reset(self) -> None:
        """Back to 100 % without announcing it (zoom is per page, like most image viewers)."""
        with handler_blocked(self._scale, self._on_scale_changed):
            self._scale.set_value(ZOOM_DEFAULT)
        self._label.set_text(f"{ZOOM_DEFAULT}%")

    def _step(self, delta: int) -> None:
        self._scale.set_value(max(ZOOM_MIN, min(ZOOM_MAX, self._scale.get_value() + delta)))
        # Don't rely solely on "value-changed" firing from set_value() above —
        # apply directly too, so the +/- buttons work correctly regardless.
        self._on_scale_changed(self._scale)

    def _on_scale_changed(self, scale: Gtk.Scale) -> None:
        self._label.set_text(f"{int(scale.get_value())}%")
        self._on_zoom_changed(self.factor)
