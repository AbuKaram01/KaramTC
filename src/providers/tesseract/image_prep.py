# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/image_prep.py — Prepares an image for Tesseract.
"""
from __future__ import annotations

import os

# A page's OCR time grows with its pixel count. 120 s is plenty for a normal
# scan (a 200-DPI A4 page is ~4 MP) but not for the 600-DPI pages the PDF tab
# can produce on a slow machine, so the limit scales with image size.
OCR_BASE_TIMEOUT_S = 120
OCR_MAX_TIMEOUT_S = 1800
_TIMEOUT_FIXED_PART_S = 60
_TIMEOUT_PER_MEGAPIXEL_S = 12

_EXIF_ORIENTATION_TAG = 0x0112
_UPRIGHT_ORIENTATIONS = (None, 0, 1)
_PNG_SAFE_MODES = ("RGB", "RGBA", "L", "LA", "1")


def ocr_timeout(image_path: str) -> float:
    """Seconds to wait for Tesseract on *image_path*: at least the base limit, more for large images."""
    try:
        from PIL import Image
        with Image.open(image_path) as image:
            megapixels = image.width * image.height / 1_000_000
    except Exception:
        return float(OCR_BASE_TIMEOUT_S)
    scaled = _TIMEOUT_FIXED_PART_S + _TIMEOUT_PER_MEGAPIXEL_S * megapixels
    return float(min(OCR_MAX_TIMEOUT_S, max(OCR_BASE_TIMEOUT_S, scaled)))


def upright_copy(image_path: str, tmp_dir: str) -> str:
    """
    Phone and camera photos are usually stored sideways with an EXIF
    "Orientation" tag telling viewers to rotate them. Tesseract ignores that
    tag and reads the raw pixels, giving gibberish for a photo that looks
    perfectly upright in any viewer.

    If *image_path* carries a rotation/flip tag, returns a physically rotated
    PNG copy inside *tmp_dir*; otherwise (or on any problem) returns
    *image_path* unchanged.
    """
    try:
        from PIL import Image, ImageOps
        with Image.open(image_path) as image:
            if image.getexif().get(_EXIF_ORIENTATION_TAG, 1) in _UPRIGHT_ORIENTATIONS:
                return image_path
            fixed = ImageOps.exif_transpose(image)
            if fixed is None or fixed is image:
                return image_path
            if fixed.mode not in _PNG_SAFE_MODES:
                fixed = fixed.convert("RGB")
            output_path = os.path.join(tmp_dir, "upright.png")
            fixed.save(output_path, "PNG")
            return output_path
    except Exception:
        return image_path
