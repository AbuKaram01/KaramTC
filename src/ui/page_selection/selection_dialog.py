# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The "Pages to extract" thumbnail picker.

Shows every page of the chosen PDF as a thumbnail with a checkbox, all checked by default. Unchecking a page excludes
it from extraction entirely: it is not classified, converted or OCR'd, and it is not present in any output.

Clicking a thumbnail opens PagePreviewDialog.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from ui.page_selection.preview_dialog import PagePreviewDialog
from ui.page_selection.rendering import iter_thumbnail_batches, picture_from_png
from ui.widgets import dim_label, handler_blocked

# Grid thumbnail width, in pixels.
_THUMB_WIDTH = 140
# Number of thumbnails handed to the UI at a time while the rest render.
_THUMB_BATCH = 24
# Height/width ratio of a thumbnail (portrait page).
_THUMB_ASPECT = 1.35


class PageSelectionDialog(Adw.Dialog):
    """Dialog that shows every page of a PDF as a thumbnail with a checkbox to include or exclude it.

    The thumbnails are rendered on a background thread in batches, so the dialog opens at once even for a long book.

    Args:
        pdf_path: The PDF to render thumbnails from.
        page_count: The total number of pages (already known by the caller).
        excluded_pages: The currently excluded zero-based pages, so that reopening shows the same selection.
        on_done: Called with the new set of excluded pages once the dialog is closed.
    """

    def __init__(self, pdf_path: str, page_count: int, excluded_pages: set[int], on_done):
        super().__init__(title="Pages to Extract")
        self.set_content_width(820)
        self.set_content_height(840)

        self._pdf_path = pdf_path
        self._page_count = page_count
        self._excluded = set(excluded_pages)
        self._on_done = on_done
        # Set when the dialog closes, so that the render thread stops.
        self._closed = False
        # Number of thumbnails shown so far.
        self._loaded = 0
        self._checks: dict[int, Gtk.CheckButton] = {}

        toolbar_view = Adw.ToolbarView()
        self.set_child(toolbar_view)
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        toolbar_view.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.set_vexpand(True)
        self._loading_box = self._build_loading_state()
        self._grid_box = self._build_grid_state()
        content.append(self._loading_box)
        content.append(self._grid_box)
        toolbar_view.set_content(content)
        toolbar_view.add_bottom_bar(self._build_action_bar())

        self.connect("closed", self._on_closed)
        threading.Thread(target=self._render_thumbnails, daemon=True).start()

    # --- Construction ---

    def _build_loading_state(self) -> Gtk.Box:
        """Shown first, while thumbnails render."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_vexpand(True)
        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        spinner.set_halign(Gtk.Align.CENTER)
        box.append(spinner)
        self._loading_label = dim_label("Rendering pages\u2026")
        box.append(self._loading_label)
        return box

    def _build_grid_state(self) -> Gtk.Box:
        """Shown once the first thumbnails are ready."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_visible(False)

        hint = dim_label("Uncheck any pages you want to leave out \u2014 click a page to see it full-size")
        hint.set_margin_top(12)
        hint.set_margin_bottom(6)
        box.append(hint)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self._flowbox = Gtk.FlowBox()
        self._flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flowbox.set_homogeneous(True)
        self._flowbox.set_row_spacing(10)
        self._flowbox.set_column_spacing(10)
        self._flowbox.set_margin_start(12)
        self._flowbox.set_margin_end(12)
        self._flowbox.set_valign(Gtk.Align.START)
        scroll.set_child(self._flowbox)
        box.append(scroll)
        return box

    def _build_action_bar(self) -> Gtk.ActionBar:
        bar = Gtk.ActionBar()
        select_all = Gtk.Button(label="Select all")
        select_all.connect("clicked", lambda *_: self._set_all(True))
        bar.pack_start(select_all)
        deselect_all = Gtk.Button(label="Deselect all")
        deselect_all.connect("clicked", lambda *_: self._set_all(False))
        bar.pack_start(deselect_all)

        self._count_label = Gtk.Label(label="")
        bar.set_center_widget(self._count_label)

        done_button = Gtk.Button(label="Done")
        done_button.add_css_class("suggested-action")
        done_button.connect("clicked", lambda *_: self.close())
        bar.pack_end(done_button)
        return bar

    # --- Thumbnail rendering (background thread) ---

    def _render_thumbnails(self) -> None:
        """Render the thumbnails on a worker thread; each batch is handed to the main loop via idle_add."""
        try:
            for batch in iter_thumbnail_batches(
                self._pdf_path, _THUMB_WIDTH, _THUMB_BATCH, lambda: self._closed,
            ):
                GLib.idle_add(self._on_thumbnails_batch, batch)
        except Exception as exc:
            GLib.idle_add(self._on_render_failed, str(exc))

    def _on_render_failed(self, message: str) -> bool:
        self._loading_label.set_text(f"Could not render page previews: {message}")
        return GLib.SOURCE_REMOVE

    def _on_thumbnails_batch(self, batch: list[tuple[int, bytes]]) -> bool:
        if self._closed:
            return GLib.SOURCE_REMOVE
        for index, png_bytes in batch:
            self._flowbox.append(self._build_card(index, png_bytes))
        self._loaded += len(batch)
        if self._loading_box.get_visible():
            self._loading_box.set_visible(False)
            self._grid_box.set_visible(True)
        self._update_count_label()
        return GLib.SOURCE_REMOVE

    def _build_card(self, index: int, png_bytes: bytes) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.set_size_request(_THUMB_WIDTH + 16, -1)

        picture = picture_from_png(png_bytes)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(_THUMB_WIDTH, int(_THUMB_WIDTH * _THUMB_ASPECT))

        # The thumbnail is a button that opens a full-size, readable preview. It is kept separate from the checkbox
        # so that previewing never toggles inclusion.
        zoom_button = Gtk.Button()
        zoom_button.set_child(picture)
        zoom_button.add_css_class("flat")
        zoom_button.add_css_class("card")
        zoom_button.set_tooltip_text("Click to view full-size")
        zoom_button.connect("clicked", lambda *_: self._open_preview(index))
        card.append(zoom_button)

        check = Gtk.CheckButton(label=f"Page {index + 1}")
        check.set_active(index not in self._excluded)
        check.set_halign(Gtk.Align.CENTER)
        check.connect("toggled", self._on_check_toggled, index)
        card.append(check)
        self._checks[index] = check
        return card

    # --- Selection ---

    def _open_preview(self, index: int) -> None:
        PagePreviewDialog(
            self._pdf_path, index, self._page_count,
            is_included=lambda page: page not in self._excluded,
            on_toggle=self._on_preview_toggle,
        ).present(self)

    def _mark(self, index: int, included: bool) -> None:
        if included:
            self._excluded.discard(index)
        else:
            self._excluded.add(index)

    def _on_preview_toggle(self, index: int, included: bool) -> None:
        """Keep the grid's checkbox in step with a toggle made in the preview."""
        self._mark(index, included)
        check = self._checks.get(index)
        if check is not None:
            with handler_blocked(check, self._on_check_toggled):
                check.set_active(included)
        self._update_count_label()

    def _on_check_toggled(self, check: Gtk.CheckButton, index: int) -> None:
        self._mark(index, check.get_active())
        self._update_count_label()

    def _set_all(self, included: bool) -> None:
        for index, check in self._checks.items():
            self._mark(index, included)
            with handler_blocked(check, self._on_check_toggled):
                check.set_active(included)
        self._update_count_label()

    def _update_count_label(self) -> None:
        included = self._page_count - len(self._excluded)
        text = f"{included} of {self._page_count} pages selected"
        if self._loaded < self._page_count:
            text += f"  \u2022  loading previews {self._loaded}/{self._page_count}\u2026"
        self._count_label.set_text(text)

    def _on_closed(self, *_) -> None:
        self._closed = True
        if self._on_done:
            self._on_done(set(self._excluded))
