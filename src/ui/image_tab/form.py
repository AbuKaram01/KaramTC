# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/image_tab/form.py — The Image tab's "choose an image" screen.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ui.image_tab.preview import PREVIEW_HEIGHT
from ui.language_selector import LanguageSelector
from ui.widgets import (
    add_file_drop_target, centered_row, dim_label, flat_text_button, labeled_button, make_icon_prefix,
    pill_button, scrolled_clamp, status_page,
)

_DEFAULT_PROGRESS_MESSAGE = "Extracting\u2026"


class ImageForm:
    """Empty state → file info + language + Extract button → progress spinner.
    Put `widget` (a scrolled page) into the tab."""

    def __init__(self, on_choose_image, on_extract, on_open_settings, on_drop):
        self.widget, clamp = scrolled_clamp(maximum_size=580, tightening_threshold=400)
        add_file_drop_target(self.widget, on_drop)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(content)

        self._build_empty_state(content, on_choose_image)
        self._build_preview(content)
        self._build_file_group(content, on_choose_image, on_open_settings)
        self._build_extract_button(content, on_extract)
        self._build_progress(content)

    # ── Construction ──────────────────────────────────────────────────

    def _build_empty_state(self, content: Gtk.Box, on_choose_image) -> None:
        self._intro = status_page(
            "image-x-generic-symbolic", "Choose an image",
            "Drag a JPEG, PNG or WebP file here or press the button below",
        )
        content.append(self._intro)
        self._choose_box = centered_row(
            pill_button("Open image\u2026", "document-open-symbolic", on_choose_image, suggested=True)
        )
        content.append(self._choose_box)

    def _build_preview(self, content: Gtk.Box) -> None:
        self._preview_frame = Gtk.Frame()
        self._preview_frame.set_overflow(Gtk.Overflow.HIDDEN)
        self._preview_frame.add_css_class("card")
        self._preview_frame.set_visible(False)
        # CONTAIN, not COVER: COVER would crop a portrait photo to a thin slice from its middle.
        self._preview_picture = Gtk.Picture()
        self._preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._preview_picture.set_size_request(-1, PREVIEW_HEIGHT)
        self._preview_picture.set_can_shrink(True)
        self._preview_frame.set_child(self._preview_picture)
        content.append(self._preview_frame)

    def _build_file_group(self, content: Gtk.Box, on_choose_image, on_open_settings) -> None:
        self._file_group = Adw.PreferencesGroup()
        self._file_group.set_visible(False)
        content.append(self._file_group)

        self._file_row = Adw.ActionRow()
        self._file_row.set_use_markup(False)        # file names may contain & or <
        self._file_row.set_title("\u2014")
        self._file_row.add_prefix(make_icon_prefix("image-x-generic-symbolic"))
        self._file_row.add_suffix(flat_text_button("Change", on_choose_image))
        self._file_group.add(self._file_row)

        self.language = LanguageSelector("Language", on_open_settings)
        self._file_group.add(self.language.row)

    def _build_extract_button(self, content: Gtk.Box, on_extract) -> None:
        self._extract_button = labeled_button("Extract text", "edit-find-symbolic")
        self._extract_button.add_css_class("pill")
        self._extract_button.add_css_class("suggested-action")
        self._extract_button.set_halign(Gtk.Align.CENTER)
        self._extract_button.set_sensitive(False)
        self._extract_button.set_visible(False)
        self._extract_button.connect("clicked", on_extract)
        content.append(self._extract_button)

    def _build_progress(self, content: Gtk.Box) -> None:
        self._progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._progress_box.set_halign(Gtk.Align.CENTER)
        self._progress_box.set_visible(False)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(20, 20)
        self._progress_box.append(self._spinner)
        self._progress_label = dim_label(_DEFAULT_PROGRESS_MESSAGE)
        self._progress_box.append(self._progress_label)
        content.append(self._progress_box)

    # ── State ─────────────────────────────────────────────────────────

    def show_image(self, name: str, size_text: str, preview_texture) -> None:
        """Shows the chosen image's details; *preview_texture* is None if it couldn't be previewed."""
        self._file_row.set_subtitle(size_text)
        self._file_row.set_title(name)
        if preview_texture is not None:
            self._preview_picture.set_paintable(preview_texture)
        self._preview_frame.set_visible(preview_texture is not None)
        self._intro.set_visible(False)
        self._choose_box.set_visible(False)
        self._file_group.set_visible(True)
        self._extract_button.set_visible(True)

    def clear(self) -> None:
        self._file_row.set_title("\u2014")
        self._file_row.set_subtitle("")
        self._preview_picture.set_paintable(None)
        self._preview_frame.set_visible(False)
        self._intro.set_visible(True)
        self._choose_box.set_visible(True)
        self._file_group.set_visible(False)
        self._extract_button.set_visible(False)
        self._extract_button.set_sensitive(False)

    def set_extract_enabled(self, enabled: bool) -> None:
        self._extract_button.set_sensitive(enabled)

    def show_progress(self, running: bool) -> None:
        self._progress_box.set_visible(running)
        if running:
            self._spinner.start()
        else:
            self._spinner.stop()
            self._progress_label.set_text(_DEFAULT_PROGRESS_MESSAGE)

    def set_progress_message(self, message: str) -> None:
        self._progress_label.set_text(message)
