# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Conversion of stored or user-edited values into valid settings.

A hand-edited settings.json or a progress file from an older version may hold anything. These functions clamp or
default such values instead of trusting them.
"""

from __future__ import annotations

from config import (
    BOOK_IMAGE_DPI, BOOK_IMAGE_DPI_RANGE,
    BOOK_IMAGE_JPEG_QUALITY, BOOK_IMAGE_JPEG_QUALITY_RANGE,
)
from core.book.constants import IMAGE_MODE_AUTO, IMAGE_MODE_ON, IMAGE_MODES


def _clamped_int(value, default: int, bounds: tuple[int, int]) -> int:
    """Round *value* to an integer within *bounds*; return *default* if it is not a number."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(bounds[0], min(bounds[1], number))


def normalize_image_dpi(value) -> int:
    """Return the DPI used to render PDF pages for OCR.

    The value is clamped to BOOK_IMAGE_DPI_RANGE. Anything that is not a number yields BOOK_IMAGE_DPI.
    """
    return _clamped_int(value, BOOK_IMAGE_DPI, BOOK_IMAGE_DPI_RANGE)


def normalize_jpeg_quality(value) -> int:
    """Return the JPEG quality of the rendered page images, clamped to BOOK_IMAGE_JPEG_QUALITY_RANGE.

    Anything that is not a number yields BOOK_IMAGE_JPEG_QUALITY.
    """
    return _clamped_int(value, BOOK_IMAGE_JPEG_QUALITY, BOOK_IMAGE_JPEG_QUALITY_RANGE)


def normalize_image_mode(value) -> str:
    """Map any stored or legacy value to one of IMAGE_MODES.

    Booleans come from the old "Force image mode" switch (True means "on", False means "auto"). Anything
    unrecognised falls back to "auto".
    """
    if value is True:
        return IMAGE_MODE_ON
    if isinstance(value, str) and value.lower() in IMAGE_MODES:
        return value.lower()
    return IMAGE_MODE_AUTO
