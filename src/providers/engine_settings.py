# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/engine_settings.py — The user's OCR engine choices, as one value.

Both tabs build OcrOptions from the same saved OCR Settings; this is the one
place that knows how those settings map onto OcrOptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from providers import tessdata_manager
from providers.ocr_types import DEFAULT_OEM, DEFAULT_PSM, TESSERACT_TOGGLE_VARIABLES, OcrOptions

SYSTEM_LANG_SOURCE = "system"
EDGES_VARIABLE = "edges_max_children_per_outline"


@dataclass
class OcrEngineSettings:
    oem: int = DEFAULT_OEM
    psm: int = DEFAULT_PSM
    preserve_interword_spaces: bool = False
    custom_params: str = ""
    lang_source: str = SYSTEM_LANG_SOURCE       # "system" or a tessdata_manager quality tier
    # Toggle variables (names in TESSERACT_TOGGLE_VARIABLES → bool) plus,
    # only when enabled, EDGES_VARIABLE → int. Saved with a PDF job as "tess_extra".
    extra_variables: dict = field(default_factory=dict)

    def to_ocr_options(
        self, want_pdf: bool = False, want_confidence: bool = True, threads: int | None = None,
    ) -> OcrOptions:
        tessdata_dir = (
            None if self.lang_source == SYSTEM_LANG_SOURCE
            else tessdata_manager.local_tessdata_dir(self.lang_source)
        )
        toggles = {name: self.extra_variables.get(name, False) for name in TESSERACT_TOGGLE_VARIABLES}
        return OcrOptions(
            oem=self.oem,
            psm=self.psm,
            preserve_interword_spaces=self.preserve_interword_spaces,
            edges_max_children_per_outline=self.extra_variables.get(EDGES_VARIABLE),
            custom_params=self.custom_params,
            tessdata_dir=tessdata_dir,
            want_pdf=want_pdf,
            want_confidence=want_confidence,
            threads=threads,
            **toggles,
        )
