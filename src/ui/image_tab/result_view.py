# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/image_tab/result_view.py — The Image tab's result screen: editable text plus actions.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ui.widgets import dim_label, flat_icon_button, labeled_button, scrolled_clamp


class ImageResultView(Gtk.Box):
    def __init__(self, on_new_image, on_copy, on_save_text, on_save_pdf):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.append(self._build_action_bar(on_new_image, on_copy, on_save_text, on_save_pdf))

        self._confidence_label = dim_label(caption=True)
        self._confidence_label.set_halign(Gtk.Align.START)
        self._confidence_label.set_margin_start(12)
        self._confidence_label.set_margin_bottom(6)
        self._confidence_label.set_visible(False)
        self.append(self._confidence_label)

        scroll, clamp = scrolled_clamp(maximum_size=700, tightening_threshold=500, margin_top=0)
        self.append(scroll)
        card = Gtk.Frame()
        card.add_css_class("card")
        card.set_overflow(Gtk.Overflow.HIDDEN)
        clamp.set_child(card)
        self._text_view = self._build_text_view()
        card.set_child(self._text_view)

    def _build_action_bar(self, on_new_image, on_copy, on_save_text, on_save_pdf) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_margin_top(12)
        bar.set_margin_bottom(6)
        bar.set_margin_start(12)
        bar.set_margin_end(12)

        new_button = labeled_button("New image", "list-add-symbolic")
        new_button.set_tooltip_text("Choose another image")
        new_button.connect("clicked", on_new_image)
        bar.append(new_button)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        bar.append(flat_icon_button("edit-copy-symbolic", "Copy text", on_copy, centered=False))
        bar.append(flat_icon_button("document-save-symbolic", "Save as text file", on_save_text, centered=False))
        self._save_pdf_button = flat_icon_button(
            "x-office-document-symbolic", "Save as searchable PDF", on_save_pdf, centered=False,
        )
        self._save_pdf_button.set_visible(False)
        bar.append(self._save_pdf_button)
        return bar

    @staticmethod
    def _build_text_view() -> Gtk.TextView:
        text_view = Gtk.TextView()
        text_view.set_editable(True)
        text_view.set_cursor_visible(True)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_top_margin(14)
        text_view.set_bottom_margin(14)
        text_view.set_left_margin(16)
        text_view.set_right_margin(16)
        text_view.add_css_class("monospace")
        return text_view

    @property
    def text(self) -> str:
        """The text as currently shown — including the user's edits."""
        buffer = self._text_view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def show_result(self, text: str, has_searchable_pdf: bool, confidence: float | None) -> None:
        self._text_view.get_buffer().set_text(text)
        self._save_pdf_button.set_visible(has_searchable_pdf)
        if confidence is None:
            self._confidence_label.set_visible(False)
            return
        self._confidence_label.set_text(f"OCR confidence: {confidence:.0f}%")
        self._confidence_label.set_visible(True)
