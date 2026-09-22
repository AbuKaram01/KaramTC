# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/ocr_types.py — The shared contract between the app and OCR providers.

OcrOptions / OcrResult give every provider one optional, uniform way to take
advanced engine settings and return text, confidence and a searchable PDF. A
provider that ignores `options` entirely still works.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_OEM = 3     # Tesseract engine mode: "Default"
DEFAULT_PSM = 3     # Tesseract page segmentation: "Fully automatic"

# Tesseract config variables exposed as their own on/off toggles. Each one is
# an OcrOptions field of the same name, a settings key "ocr_<name>", and is
# only passed to Tesseract when switched on — otherwise Tesseract's own
# built-in default applies untouched.
TESSERACT_TOGGLE_VARIABLES = (
    "chop_enable",
    "use_new_state_cost",
    "segment_segcost_rating",
    "enable_new_segsearch",
    "language_model_ngram_on",
    "textord_force_make_prop_words",
)


class OcrPageError(RuntimeError):
    """
    OCR failed for *this image* — it timed out, or the engine crashed or could
    not read it — as opposed to a problem with the setup (a missing language
    pack, Tesseract not installed, …) that would fail every page alike.

    The distinction lets a long job skip one bad page and carry on, while still
    stopping at once for failures that continuing could never fix.
    """


@dataclass
class OcrOptions:
    """Advanced OCR tuning knobs. A provider may ignore any field it does not
    understand; OcrOptions() (all defaults) reproduces the fixed default behavior."""
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
    edges_max_children_per_outline: int | None = None   # None = don't override

    custom_params: str = ""             # raw "key=value; key2=value2" pairs
    tessdata_dir: str | None = None     # overrides where language data is loaded from
    want_pdf: bool = False              # also produce a searchable PDF alongside the text
    threads: int | None = None          # CPU threads the engine may use; None = engine decides
    want_confidence: bool = True        # also compute a mean-confidence score


@dataclass
class OcrResult:
    """Uniform result returned by every provider's ocr() function."""
    text: str
    confidence: float | None = None     # 0-100, or None if unavailable
    pdf_bytes: bytes | None = None      # set only if OcrOptions.want_pdf was requested
