# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/page_selection/rendering.py — Renders PDF pages to PNG for thumbnails and previews.

Everything here is meant to run off the GTK main thread, except
picture_from_png(), which builds a widget.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from core.pdf_backend import fitz

_PORTRAIT_ASPECT = 1.35     # fallback height/width of a page we could not render


def _page_png(page, target_width: int) -> bytes:
    """One page as PNG bytes, scaled to roughly *target_width* pixels wide."""
    scale = target_width / page.rect.width if page.rect.width else 1.0
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")


def render_page_png(pdf_path: str, index: int, target_width: int) -> bytes:
    """Renders one page to PNG bytes at roughly *target_width* pixels wide."""
    doc = fitz.open(pdf_path)
    try:
        return _page_png(doc.load_page(index), target_width)
    finally:
        doc.close()


def iter_thumbnail_batches(
    pdf_path: str, target_width: int, batch_size: int, is_cancelled: Callable[[], bool],
) -> Iterator[list[tuple[int, bytes]]]:
    """
    Yields lists of (page index, PNG bytes), so the first pages can be shown
    immediately even in a 1000-page book. Stops as soon as *is_cancelled()*,
    and one unrenderable page only costs that page its picture (empty bytes).
    Raises if the PDF itself can't be opened.
    """
    doc = fitz.open(pdf_path)
    try:
        batch: list[tuple[int, bytes]] = []
        for index in range(doc.page_count):
            if is_cancelled():
                return
            try:
                batch.append((index, _page_png(doc.load_page(index), target_width)))
            except Exception:
                batch.append((index, b""))      # shown as an empty picture, still selectable
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
    finally:
        doc.close()


def texture_from_png(png_bytes: bytes) -> Gdk.Texture | None:
    try:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(png_bytes))
    except Exception:
        return None


def picture_from_png(png_bytes: bytes) -> Gtk.Picture:
    """A picture of the PNG, or an empty one if it can't be decoded."""
    texture = texture_from_png(png_bytes)
    return Gtk.Picture.new_for_paintable(texture) if texture else Gtk.Picture()


def fallback_preview_size(preview_width: int) -> tuple[int, int]:
    return preview_width, int(preview_width * _PORTRAIT_ASPECT)
