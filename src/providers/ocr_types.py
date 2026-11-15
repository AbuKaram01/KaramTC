# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The shared contract between the app and the OCR providers.

OcrOptions and OcrResult give every provider one optional, uniform way to take advanced engine settings and to return
text, confidence and a searchable PDF. A provider that ignores `options` entirely still works.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tesseract engine mode: "Default".
DEFAULT_OEM = 3
# Tesseract page segmentation mode: "Fully automatic".
DEFAULT_PSM = 3

# Tesseract config variables exposed as their own on/off toggles. Each one is an OcrOptions field of the same name and
# a settings key "ocr_<name>". It is passed to Tesseract only when switched on; otherwise Tesseract's own built-in
# default applies untouched.
TESSERACT_TOGGLE_VARIABLES = (
    "chop_enable",
    "use_new_state_cost",
    "segment_segcost_rating",
    "enable_new_segsearch",
    "language_model_ngram_on",
    "textord_force_make_prop_words",
)


class OcrPageError(RuntimeError):
    """OCR failed for this one image, as opposed to a problem with the setup.

    The image timed out, or the engine crashed on it or could not read it. A setup problem (a missing language pack,
    Tesseract not installed, ...) would fail every page alike.

    The distinction lets a long job skip one bad page and carry on, while still stopping at once for failures that
    continuing could never fix.
    """


@dataclass
class OcrOptions:
    """Advanced OCR tuning knobs.

    A provider may ignore any field it does not understand; OcrOptions() (all defaults) reproduces the fixed default
    behavior.
    """

    oem: int = DEFAULT_OEM
    psm: int = DEFAULT_PSM
    preserve_interword_spaces: bool = False

    # One field per name in TESSERACT_TOGGLE_VARIABLES.
    chop_enable: bool = False
    use_new_state_cost: bool = False
    segment_segcost_rating: bool = False
    enable_new_segsearch: bool = False
    language_model_ngram_on: bool = False
    textord_force_make_prop_words: bool = False
    # None means "do not override".
    edges_max_children_per_outline: int | None = None

    # Raw "key=value; key2=value2" pairs.
    custom_params: str = ""
    # Overrides where language data is loaded from.
    tessdata_dir: str | None = None
    # Also produce a searchable PDF alongside the text.
    want_pdf: bool = False
    # CPU threads the engine may use; None lets the engine decide.
    threads: int | None = None
    # Also compute a mean-confidence score.
    want_confidence: bool = True


@dataclass
class OcrResult:
    """The uniform result returned by every provider's ocr() function."""

    text: str
    # Mean confidence from 0 to 100, or None if unavailable.
    confidence: float | None = None
    # Set only if OcrOptions.want_pdf was requested.
    pdf_bytes: bytes | None = None
