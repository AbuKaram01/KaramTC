# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/page_selection/preview_dialog.py — Full-size, readable render of a single page.
"""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from ui.page_selection.rendering import fallback_preview_size, render_page_png, texture_from_png
from ui.page_selection.zoom_bar import ZoomBar
from ui.widgets import dim_label, handler_blocked

# Full-size render width in pixels — high enough that zooming has real detail
# to zoom into rather than just blowing up a fixed-resolution image.
PREVIEW_WIDTH = 1400


class PagePreviewDialog(Adw.Dialog):
    """
    A page at full size, with Previous/Next navigation and its own
    include/exclude checkbox, so a page can actually be read before deciding
    to keep it.

    :param is_included: callable(index) -> bool, queries the current state.
    :param on_toggle:   callable(index, included) — reports a change back to
                        whoever opened this dialog (the page grid).
    """

    def __init__(self, pdf_path: str, index: int, page_count: int, is_included, on_toggle):
        super().__init__(title=f"Page {index + 1} of {page_count}")
        # Large enough that a page fits with little scrolling on a typical
        # laptop screen — not maximized, since a dialog that covers the whole
        # display is its own kind of annoying.
        self.set_content_width(920)
        self.set_content_height(940)

        self._pdf_path = pdf_path
        self._index = index
        self._page_count = page_count
        self._is_included = is_included
        self._on_toggle = on_toggle
        self._base_size: tuple[int, int] | None = None   # native pixels of the current render = 100 % zoom

        toolbar_view = Adw.ToolbarView()
        self.set_child(toolbar_view)
        toolbar_view.add_top_bar(Adw.HeaderBar())
        toolbar_view.set_content(self._build_stack())
        self._zoom_bar = ZoomBar(self._apply_zoom)
        toolbar_view.add_bottom_bar(self._zoom_bar)
        toolbar_view.add_bottom_bar(self._build_action_bar())

        self._load_page(index)

    # ── Construction ──────────────────────────────────────────────────

    def _build_stack(self) -> Gtk.Stack:
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_vexpand(True)

        spinner = Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        self._stack.add_named(spinner, "loading")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._picture_holder = Adw.Bin()
        scroll.set_child(self._picture_holder)
        self._stack.add_named(scroll, "image")
        return self._stack

    def _build_action_bar(self) -> Gtk.ActionBar:
        bar = Gtk.ActionBar()
        self._prev_button = Gtk.Button(label="\u2190 Previous")
        self._prev_button.connect("clicked", lambda *_: self._go(-1))
        bar.pack_start(self._prev_button)
        self._next_button = Gtk.Button(label="Next \u2192")
        self._next_button.connect("clicked", lambda *_: self._go(1))
        bar.pack_start(self._next_button)

        self._include_check = Gtk.CheckButton(label="Include this page")
        self._include_check.connect("toggled", self._on_check_toggled)
        bar.set_center_widget(self._include_check)

        close_button = Gtk.Button(label="Close")
        close_button.add_css_class("suggested-action")
        close_button.connect("clicked", lambda *_: self.close())
        bar.pack_end(close_button)
        return bar

    # ── Navigation and rendering ──────────────────────────────────────

    def _load_page(self, index: int) -> None:
        self._index = index
        self.set_title(f"Page {index + 1} of {self._page_count}")
        self._prev_button.set_sensitive(index > 0)
        self._next_button.set_sensitive(index < self._page_count - 1)
        # Only reflecting state here, not changing it — don't report it back.
        with handler_blocked(self._include_check, self._on_check_toggled):
            self._include_check.set_active(self._is_included(index))

        # Zoom is per page: don't carry a zoomed-in view over to a page that
        # hasn't been seen yet. Reset silently — the picture is about to be replaced.
        self._base_size = None
        self._zoom_bar.reset()
        self._stack.set_visible_child_name("loading")
        threading.Thread(target=self._render, args=(index,), daemon=True).start()

    def _render(self, index: int) -> None:
        try:
            png_bytes = render_page_png(self._pdf_path, index, PREVIEW_WIDTH)
        except Exception as exc:
            GLib.idle_add(self._on_render_failed, str(exc))
            return
        GLib.idle_add(self._on_rendered, index, png_bytes)

    def _on_rendered(self, index: int, png_bytes: bytes) -> bool:
        if index != self._index:
            return GLib.SOURCE_REMOVE       # user already navigated on — discard this stale render
        texture = texture_from_png(png_bytes)
        picture = Gtk.Picture.new_for_paintable(texture) if texture else Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_can_shrink(True)
        self._base_size = (
            (texture.get_width(), texture.get_height()) if texture else fallback_preview_size(PREVIEW_WIDTH)
        )
        self._picture_holder.set_child(picture)
        self._apply_zoom(self._zoom_bar.factor)
        self._stack.set_visible_child_name("image")
        return GLib.SOURCE_REMOVE

    def _on_render_failed(self, message: str) -> bool:
        self._picture_holder.set_child(dim_label(f"Could not render this page: {message}"))
        self._stack.set_visible_child_name("image")
        return GLib.SOURCE_REMOVE

    def _go(self, delta: int) -> None:
        new_index = self._index + delta
        if 0 <= new_index < self._page_count:
            self._load_page(new_index)

    def _on_check_toggled(self, check: Gtk.CheckButton) -> None:
        if self._on_toggle:
            self._on_toggle(self._index, check.get_active())

    def _apply_zoom(self, factor: float) -> None:
        """Resizes the already-rendered picture — no re-render needed."""
        picture = self._picture_holder.get_child()
        if self._base_size is None or picture is None:
            return
        width, height = self._base_size
        picture.set_size_request(int(width * factor), int(height * factor))
