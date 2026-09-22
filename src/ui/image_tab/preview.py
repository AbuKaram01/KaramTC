# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/image_tab/preview.py — The fixed-size preview picture of the chosen image.
"""
from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf

# Every preview is drawn on a canvas of exactly this size, so the preview's
# height never depends on the photo.
PREVIEW_WIDTH, PREVIEW_HEIGHT = 560, 180
_MAX_LOAD_SIDE = 1200
_TRANSPARENT = 0x00000000


def build_preview_texture(path: str) -> Gdk.Texture:
    """
    The image, scaled to fit and centred on a transparent PREVIEW_WIDTH x
    PREVIEW_HEIGHT canvas. Raises if the file can't be read as an image.

    Phone photos are stored sideways with an EXIF rotation tag; the preview is
    shown upright (the OCR side applies the same rotation, see
    providers/tesseract/image_prep.py). The rotation has to happen before
    fitting the box, since it swaps width and height.
    """
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, _MAX_LOAD_SIDE, _MAX_LOAD_SIDE, True)
    pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
    factor = min(PREVIEW_WIDTH / pixbuf.get_width(), PREVIEW_HEIGHT / pixbuf.get_height())
    width = max(1, int(pixbuf.get_width() * factor))
    height = max(1, int(pixbuf.get_height() * factor))
    scaled = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)

    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, PREVIEW_WIDTH, PREVIEW_HEIGHT)
    canvas.fill(_TRANSPARENT)
    x, y = (PREVIEW_WIDTH - width) // 2, (PREVIEW_HEIGHT - height) // 2
    scaled.composite(canvas, x, y, width, height, x, y, 1, 1, GdkPixbuf.InterpType.BILINEAR, 255)
    return Gdk.Texture.new_for_pixbuf(canvas)
