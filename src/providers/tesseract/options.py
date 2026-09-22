# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/options.py — Engine mode (OEM) and page segmentation (PSM).

Both are chosen in the OCR Settings dialog and travel to the engine through
OcrOptions (see providers/ocr_types.py).
"""
from __future__ import annotations

from providers.ocr_types import DEFAULT_OEM, DEFAULT_PSM

# Each entry is (value, short_label, full_description). The short label is
# what the ComboRow shows (it truncates long text); the description appears
# as the row's subtitle once a value is selected.
OEM_OPTIONS: list[tuple[int, str, str]] = [
    (0, "Legacy only",        "Legacy engine only \u2014 the older, non-neural Tesseract engine"),
    (1, "Neural net (LSTM)",  "Neural net (LSTM) only \u2014 usually the most accurate option"),
    (2, "Legacy + LSTM",      "Legacy + LSTM combined \u2014 runs both and merges results"),
    (3, "Default",            "Default \u2014 whichever engine is available on this system"),
]

# PSM 0 ("OSD only") and PSM 2 ("Auto, no OSD/OCR") are deliberately absent:
# neither one produces any text. PSM 0 only prints orientation/script info and
# exits with an error on LSTM-only language data ("OSD requires a model for the
# legacy engine"); PSM 2 exits successfully but writes no output file. This app
# exists to extract text, so offering them just led to empty or failed runs.
PSM_OPTIONS: list[tuple[int, str, str]] = [
    (1,  "Auto + OSD",             "Automatic page segmentation, with orientation detection (needs osd data)"),
    (3,  "Fully automatic",        "Fully automatic page segmentation, no orientation detection (default)"),
    (4,  "Single column",          "Assume a single column of text of variable sizes"),
    (5,  "Single vertical block",  "Assume a single uniform block of vertically aligned text"),
    (6,  "Single block",           "Assume a single uniform block of text"),
    (7,  "Single line",            "Treat the image as a single text line"),
    (8,  "Single word",            "Treat the image as a single word"),
    (9,  "Single word (circle)",   "Treat the image as a single word in a circle"),
    (10, "Single character",       "Treat the image as a single character"),
    (11, "Sparse text",            "Sparse text \u2014 find as much text as possible, no particular order"),
    (12, "Sparse text + OSD",      "Sparse text with orientation detection (needs osd data)"),
    (13, "Raw line",               "Raw line \u2014 bypass Tesseract-specific heuristics"),
]

# Modes that make Tesseract load osd.traineddata (orientation/script detection).
# That file is not part of any language pack — see providers/tessdata_manager.py.
PSM_NEEDS_OSD = frozenset({1, 12})

_VALID_OEM_VALUES = frozenset(value for value, _label, _desc in OEM_OPTIONS)
_VALID_PSM_VALUES = frozenset(value for value, _label, _desc in PSM_OPTIONS)


def _as_valid_choice(value, valid_values: frozenset[int], default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value in valid_values else default


def normalize_oem(value) -> int:
    """*value* if it is a selectable engine mode, otherwise the default."""
    return _as_valid_choice(value, _VALID_OEM_VALUES, DEFAULT_OEM)


def normalize_psm(value) -> int:
    """
    *value* if it is a selectable PSM, otherwise the default.

    Settings and resumable PDF progress files saved by earlier versions may
    still hold PSM 0 or 2 (removed above) — this keeps them working instead
    of producing empty output.
    """
    return _as_valid_choice(value, _VALID_PSM_VALUES, DEFAULT_PSM)


def psm_needs_osd(value: int) -> bool:
    """True if this page segmentation mode requires osd.traineddata."""
    return value in PSM_NEEDS_OSD


def psm_index(value) -> int:
    """Index of *value* (normalized) in PSM_OPTIONS — for UI combo rows."""
    normalized = normalize_psm(value)
    return next(i for i, (psm, _label, _desc) in enumerate(PSM_OPTIONS) if psm == normalized)
