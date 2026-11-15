# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Rendering of PDF pages to PNG for thumbnails and previews.

Everything here is meant to run off the GTK main thread, except picture_from_png(), which builds a widget.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from core.pdf_backend import fitz

# Fallback height/width ratio for a page that could not be rendered.
_PORTRAIT_ASPECT = 1.35


def _page_png(page, target_width: int) -> bytes:
    """Return one page as PNG bytes, scaled to roughly *target_width* pixels wide."""
    scale = target_width / page.rect.width if page.rect.width else 1.0
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")


def render_page_png(pdf_path: str, index: int, target_width: int) -> bytes:
    """Render one page of a PDF to PNG bytes at roughly *target_width* pixels wide."""
    doc = fitz.open(pdf_path)
    try:
        return _page_png(doc.load_page(index), target_width)
    finally:
        doc.close()


def iter_thumbnail_batches(
    pdf_path: str, target_width: int, batch_size: int, is_cancelled: Callable[[], bool],
) -> Iterator[list[tuple[int, bytes]]]:
    """Yield lists of (page index, PNG bytes) for all pages of a PDF.

    Delivering the thumbnails in batches lets the first pages be shown immediately, even in a 1000-page book. The
    generator stops as soon as *is_cancelled()* returns true. One unrenderable page only costs that page its picture
    (empty bytes).

    Args:
        pdf_path: The PDF file to render.
        target_width: The thumbnail width in pixels.
        batch_size: The number of pages per yielded list; the last list may be shorter.
        is_cancelled: Polled before each page; returns True to stop early.

    Raises:
        Exception: The PDF itself cannot be opened (raised by the PDF backend on the first iteration).
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
                # An empty picture is shown instead; the page stays selectable.
                batch.append((index, b""))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
    finally:
        doc.close()


def texture_from_png(png_bytes: bytes) -> Gdk.Texture | None:
    """Decode PNG bytes into a texture, or return None if they cannot be decoded."""
    try:
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(png_bytes))
    except Exception:
        return None


def picture_from_png(png_bytes: bytes) -> Gtk.Picture:
    """Return a picture widget showing the PNG, or an empty one if it cannot be decoded."""
    texture = texture_from_png(png_bytes)
    return Gtk.Picture.new_for_paintable(texture) if texture else Gtk.Picture()


def fallback_preview_size(preview_width: int) -> tuple[int, int]:
    """Return the (width, height) to assume for a page whose render could not be decoded, in portrait format."""
    return preview_width, int(preview_width * _PORTRAIT_ASPECT)
